"""Build ``TranscriptEditStartupInventory`` from dossier transcription run artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from domains.mapping.transcript_edit.payloads.startup_inventory import (
    MissingResource,
    SourceImageRefDescriptor,
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)

from .draft_persistence import resolve_workspace_key
from .paths import (
    UnsafeArtifactPathSegmentError,
    association_path,
    require_safe_workspace_relative_path,
    raw_drafts_dir,
    run_json_path,
    transcript_edit_latest_pointer_path,
    transcript_edit_manifest_path,
    transcript_edit_output_path,
    transcript_edit_workspace_root,
    transcription_run_dir,
)

_T0_REF_PREFIX = "t0:raw:"
_WORKING_REF = "transcript_edit:working"
_OUTPUT_REF = "transcript_edit:output"
_DUP_SUFFIX = re.compile(r"\.v\d+\.json$", re.IGNORECASE)


def _load_json(path: Path) -> Any | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _flatten_preview(data: dict[str, Any], max_len: int = 220) -> str | None:
    bodies: list[str] = []
    for sec in data.get("sections") or []:
        if isinstance(sec, dict) and sec.get("body"):
            bodies.append(str(sec["body"]))
    if not bodies:
        for key in ("text", "transcript", "body"):
            if data.get(key):
                bodies.append(str(data[key]))
                break
    blob = "\n".join(bodies).strip()
    if not blob:
        return None
    if len(blob) > max_len:
        return blob[:max_len] + "…"
    return blob


def _section_count(data: dict[str, Any]) -> int | None:
    sections = data.get("sections")
    if isinstance(sections, list):
        return len(sections)
    return None


def _artifact_fingerprint(
    *,
    run_payload: dict[str, Any] | None,
    peer_stems: tuple[str, ...],
) -> str | None:
    try:
        run_blob = json.dumps(run_payload or {}, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256()
        h.update(run_blob.encode("utf-8"))
        h.update(("\n".join(sorted(peer_stems))).encode("utf-8"))
        return h.hexdigest()[:20]
    except Exception:
        return None


def _is_legacy_pointer_stem(stem: str, transcription_id: str) -> bool:
    """Bare ``<transcription_id>.json`` in raw/ is a head-era alias, not a peer T0 pass."""
    return stem.strip() == transcription_id.strip()


def _load_association_slice(dossier_id: str, transcription_id: str) -> tuple[dict[str, Any] | None, list[MissingResource]]:
    missing: list[MissingResource] = []
    try:
        path = association_path(dossier_id)
    except UnsafeArtifactPathSegmentError as exc:
        missing.append(
            MissingResource(
                code="launch_scope_path_invalid",
                message="Dossier id is not safe for association file paths.",
                detail=str(exc),
            )
        )
        return None, missing
    if not path.is_file():
        missing.append(
            MissingResource(
                code="association_file_missing",
                message="No association record for dossier.",
                detail=str(path),
            )
        )
        return None, missing
    root = _load_json(path)
    if not isinstance(root, dict):
        missing.append(
            MissingResource(
                code="association_file_invalid",
                message="Association JSON was not an object.",
                detail=str(path),
            )
        )
        return None, missing
    for row in root.get("associations") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("transcription_id") or "").strip() == transcription_id:
            return row, missing
    missing.append(
        MissingResource(
            code="transcription_not_in_associations",
            message="Transcription id not listed in dossier associations.",
            detail=transcription_id,
        )
    )
    return None, missing


def _source_image_descriptors(
    dossier_id: str,
    transcription_id: str,
    assoc_row: dict[str, Any] | None,
) -> tuple[SourceImageRefDescriptor, ...]:
    if not assoc_row:
        return ()
    meta = assoc_row.get("metadata")
    if not isinstance(meta, dict):
        return ()
    images = meta.get("images")
    if not isinstance(images, dict):
        return ()
    out: list[SourceImageRefDescriptor] = []
    if images.get("original_path") or images.get("original_url"):
        base = Path(str(images.get("original_path") or "")).name or None
        out.append(
            SourceImageRefDescriptor(
                ref_id=f"image:assoc:{transcription_id}:original",
                role="source_original",
                basename=base,
                storage_hint="dossiers_images_original",
            )
        )
    if images.get("processed_path") or images.get("processed_url"):
        proc_path = str(images.get("processed_path") or "")
        base = Path(proc_path).name if proc_path else None
        out.append(
            SourceImageRefDescriptor(
                ref_id=f"image:assoc:{transcription_id}:processed",
                role="source_processed",
                basename=base,
                storage_hint="dossiers_images_processed_or_temp",
            )
        )
    return tuple(out)


def _peer_json_paths(raw_dir: Path) -> list[Path]:
    if not raw_dir.is_dir():
        return []
    return [
        p
        for p in sorted(raw_dir.glob("*.json"))
        if p.is_file() and not _DUP_SUFFIX.search(p.name)
    ]


def _descriptor_for_peer_path(path: Path, *, listed_in_run_json: bool) -> T0DraftDescriptor | None:
    data = _load_json(path)
    if not isinstance(data, dict):
        return None
    stem = path.stem
    try:
        byte_length = path.stat().st_size
    except OSError:
        byte_length = None
    return T0DraftDescriptor(
        ref_id=f"{_T0_REF_PREFIX}{stem}",
        variant_label=stem,
        source_file_stem=stem,
        listed_in_run_json=listed_in_run_json,
        byte_length=byte_length,
        section_count=_section_count(data),
        snippet_preview=_flatten_preview(data),
    )


def _discover_t0_descriptors(
    *,
    raw_dir: Path,
    transcription_id: str,
    completed: list[str],
    completed_is_authoritative: bool,
    missing: list[MissingResource],
) -> tuple[T0DraftDescriptor, ...]:
    """
    Peer T0 set:
    - When ``run.json`` supplies a non-empty ``completed_drafts`` list, that list is canonical:
      only those stems (with files present) are peers; extras on disk are mismatches; missing files are gaps.
    - Otherwise, scan ``raw/*.json`` excluding version sidecars and the legacy pointer alias ``<transcription_id>.json``.
    """
    transcription_id = str(transcription_id).strip()
    descriptors: list[T0DraftDescriptor] = []
    completed_ordered = [str(x).strip() for x in completed if str(x).strip()]
    completed_set = set(completed_ordered)

    if completed_is_authoritative and completed_ordered:
        for did in completed_ordered:
            if _is_legacy_pointer_stem(did, transcription_id):
                missing.append(
                    MissingResource(
                        code="completed_drafts_contains_pointer_alias",
                        message="completed_drafts lists the bare transcription id (legacy pointer alias), not a peer T0 pass.",
                        detail=did,
                    )
                )
                continue
            path = raw_dir / f"{did}.json"
            if not path.is_file():
                missing.append(
                    MissingResource(
                        code="t0_peer_file_missing",
                        message="completed_drafts lists a draft id with no matching raw JSON file.",
                        detail=did,
                    )
                )
                continue
            desc = _descriptor_for_peer_path(path, listed_in_run_json=True)
            if desc:
                descriptors.append(desc)

        disk_stems = {p.stem for p in _peer_json_paths(raw_dir)}
        for stem in sorted(disk_stems):
            if _is_legacy_pointer_stem(stem, transcription_id):
                continue
            if stem not in completed_set:
                missing.append(
                    MissingResource(
                        code="t0_raw_file_not_in_completed_drafts",
                        message="raw/ contains a JSON draft not listed in run.json completed_drafts.",
                        detail=stem,
                    )
                )
        ptr = raw_dir / f"{transcription_id}.json"
        if ptr.is_file():
            missing.append(
                MissingResource(
                    code="t0_legacy_pointer_file_present",
                    message="Legacy raw pointer file exists; excluded from peer T0 inventory (not an independent pass).",
                    detail=ptr.name,
                )
            )
        return tuple(descriptors)

    pointer_only = False
    paths = _peer_json_paths(raw_dir)
    candidates = [p for p in paths if not _is_legacy_pointer_stem(p.stem, transcription_id)]
    if not candidates and raw_dir.is_dir():
        ptr = raw_dir / f"{transcription_id}.json"
        if ptr.is_file():
            pointer_only = True
            missing.append(
                MissingResource(
                    code="t0_only_legacy_pointer_no_peer_drafts",
                    message="Only the legacy raw pointer alias exists; no peer T0 draft files to inventory.",
                    detail=str(ptr),
                )
            )

    for path in candidates:
        desc = _descriptor_for_peer_path(path, listed_in_run_json=path.stem in completed_set)
        if desc:
            descriptors.append(desc)

    if not descriptors and raw_dir.is_dir() and not pointer_only:
        missing.append(
            MissingResource(
                code="no_t0_raw_drafts_found",
                message="No readable peer T0 JSON drafts found under raw/.",
                detail=str(raw_dir),
            )
        )

    return tuple(descriptors)


def _transcript_edit_inventory(
    dossier_id: str,
    transcription_id: str,
    workspace_key: str | None,
) -> TranscriptEditDraftInventory:
    """
    Ref-first transcript-edit draft inventory under ``artifacts/transcript_edit/...``.
    Requires ``workspace_key`` (``workspace_id`` or ``run_id`` from scope); otherwise empty.
    """
    if not workspace_key:
        return TranscriptEditDraftInventory()

    latest_path = transcript_edit_latest_pointer_path(dossier_id, transcription_id, workspace_key)
    output_path = transcript_edit_output_path(dossier_id, transcription_id, workspace_key)
    manifest_path = transcript_edit_manifest_path(dossier_id, transcription_id, workspace_key)

    working_exists = False
    working_saved_at: str | None = None
    if latest_path.is_file():
        ptr = _load_json(latest_path)
        if isinstance(ptr, dict) and ptr.get("relative_path"):
            try:
                rel = require_safe_workspace_relative_path(str(ptr["relative_path"]))
                target = transcript_edit_workspace_root(dossier_id, transcription_id, workspace_key) / rel
                working_exists = target.is_file()
            except UnsafeArtifactPathSegmentError:
                working_exists = False
            if isinstance(ptr.get("saved_at"), str):
                working_saved_at = ptr["saved_at"]

    manifest = _load_json(manifest_path)
    working_latest_revision: int | None = None
    working_revision_count: int | None = None
    output_published_at: str | None = None
    if isinstance(manifest, dict):
        lr = manifest.get("latest_revision")
        if isinstance(lr, int) or (isinstance(lr, str) and str(lr).isdigit()):
            working_latest_revision = int(lr)
        rc = manifest.get("revision_count")
        if isinstance(rc, int) or (isinstance(rc, str) and str(rc).isdigit()):
            working_revision_count = int(rc)
        op = manifest.get("output_published_at")
        if isinstance(op, str) and op.strip():
            output_published_at = op.strip()

    return TranscriptEditDraftInventory(
        working_draft_exists=working_exists,
        working_draft_ref=_WORKING_REF if working_exists else None,
        output_draft_exists=output_path.is_file(),
        output_draft_ref=_OUTPUT_REF if output_path.is_file() else None,
        working_latest_revision=working_latest_revision,
        working_revision_count=working_revision_count,
        working_saved_at=working_saved_at,
        output_published_at=output_published_at,
    )


def build_transcript_edit_startup_inventory(
    *,
    dossier_id: str,
    transcription_id: str,
    segment_id: str | None = None,
    run_id: str | None = None,
    workspace_id: str | None = None,
) -> TranscriptEditStartupInventory:
    """Scan run folder + association metadata; never reads ``head.json`` for the inventory."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    missing: list[MissingResource] = []

    try:
        run_dir = transcription_run_dir(dossier_id, transcription_id)
    except UnsafeArtifactPathSegmentError as exc:
        missing.append(
            MissingResource(
                code="launch_scope_path_invalid",
                message="Dossier or transcription id is not safe for filesystem paths under views/transcriptions.",
                detail=str(exc),
            )
        )
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                segment_id=segment_id,
                run_id=run_id,
                workspace_id=workspace_id,
            ),
            missing_resources=tuple(missing),
        )
    if not run_dir.is_dir():
        missing.append(
            MissingResource(
                code="transcription_run_dir_missing",
                message="Transcription run directory does not exist.",
                detail=str(run_dir),
            )
        )
        return TranscriptEditStartupInventory(
            scope=TranscriptEditScope(
                dossier_id=dossier_id,
                transcription_id=transcription_id,
                segment_id=segment_id,
                run_id=run_id,
                workspace_id=workspace_id,
            ),
            missing_resources=tuple(missing),
        )

    run_path = run_json_path(dossier_id, transcription_id)
    run_payload = _load_json(run_path)
    completed: list[str] = []
    completed_is_authoritative = False
    run_dict: dict[str, Any] | None = None

    if run_payload is None:
        missing.append(
            MissingResource(
                code="run_json_missing_or_unreadable",
                message="run.json missing or not valid JSON.",
                detail=str(run_path),
            )
        )
    elif not isinstance(run_payload, dict):
        missing.append(
            MissingResource(
                code="run_json_invalid_shape",
                message="run.json root was not an object.",
                detail=str(run_path),
            )
        )
    else:
        run_dict = run_payload
        if "completed_drafts" not in run_payload:
            missing.append(
                MissingResource(
                    code="run_json_completed_drafts_missing",
                    message="run.json has no completed_drafts key; falling back to raw/ scan (excluding pointer alias).",
                    detail=str(run_path),
                )
            )
        else:
            raw_cd = run_payload.get("completed_drafts")
            if isinstance(raw_cd, list):
                completed = [str(x) for x in raw_cd]
                completed_is_authoritative = len(completed) > 0
            else:
                missing.append(
                    MissingResource(
                        code="run_json_completed_drafts_invalid_type",
                        message="run.json completed_drafts is not a list; falling back to raw/ scan.",
                        detail=str(run_path),
                    )
                )

    assoc_row, assoc_missing = _load_association_slice(dossier_id, transcription_id)
    missing.extend(assoc_missing)

    raw_dir = raw_drafts_dir(dossier_id, transcription_id)
    t0 = _discover_t0_descriptors(
        raw_dir=raw_dir,
        transcription_id=transcription_id,
        completed=completed,
        completed_is_authoritative=completed_is_authoritative,
        missing=missing,
    )

    images = _source_image_descriptors(dossier_id, transcription_id, assoc_row)
    if not images and assoc_row is not None:
        missing.append(
            MissingResource(
                code="no_source_image_metadata",
                message="Association exists but no image paths/urls were recorded.",
                detail=transcription_id,
            )
        )

    fp = _artifact_fingerprint(
        run_payload=run_dict,
        peer_stems=tuple(d.source_file_stem for d in t0),
    )

    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)

    try:
        te_drafts = _transcript_edit_inventory(dossier_id, transcription_id, workspace_key)
    except UnsafeArtifactPathSegmentError as exc:
        missing.append(
            MissingResource(
                code="transcript_edit_scope_path_invalid",
                message="Transcript-edit workspace path used invalid dossier, transcription, or workspace segments.",
                detail=str(exc),
            )
        )
        te_drafts = TranscriptEditDraftInventory()

    return TranscriptEditStartupInventory(
        scope=TranscriptEditScope(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            segment_id=segment_id,
            run_id=run_id,
            workspace_id=workspace_id,
        ),
        source_images=images,
        t0_drafts=t0,
        transcript_edit_drafts=te_drafts,
        artifact_fingerprint=fp,
        missing_resources=tuple(missing),
    )
