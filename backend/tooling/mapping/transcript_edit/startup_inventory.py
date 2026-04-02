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

from .paths import (
    association_path,
    raw_drafts_dir,
    run_json_path,
    transcript_edit_dir,
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


def _artifact_fingerprint(raw_dir: Path, run_payload: dict[str, Any] | None) -> str | None:
    try:
        names = sorted(
            p.name
            for p in raw_dir.glob("*.json")
            if p.is_file() and not _DUP_SUFFIX.search(p.name)
        )
        run_blob = json.dumps(run_payload or {}, sort_keys=True, ensure_ascii=False)
        h = hashlib.sha256()
        h.update(run_blob.encode("utf-8"))
        h.update(("\n".join(names)).encode("utf-8"))
        return h.hexdigest()[:20]
    except Exception:
        return None


def _load_association_slice(dossier_id: str, transcription_id: str) -> tuple[dict[str, Any] | None, list[MissingResource]]:
    missing: list[MissingResource] = []
    path = association_path(dossier_id)
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


def _discover_t0_descriptors(
    raw_dir: Path,
    completed: list[str],
) -> tuple[T0DraftDescriptor, ...]:
    completed_set = {str(x).strip() for x in completed if str(x).strip()}
    seen_stems: set[str] = set()
    descriptors: list[T0DraftDescriptor] = []

    candidates: list[Path] = []
    if raw_dir.is_dir():
        for p in sorted(raw_dir.glob("*.json")):
            if not p.is_file() or _DUP_SUFFIX.search(p.name):
                continue
            candidates.append(p)

    for path in candidates:
        stem = path.stem
        if stem in seen_stems:
            continue
        seen_stems.add(stem)
        data = _load_json(path)
        if not isinstance(data, dict):
            continue
        listed = stem in completed_set
        ref_id = f"{_T0_REF_PREFIX}{stem}"
        try:
            byte_length = path.stat().st_size
        except OSError:
            byte_length = None
        descriptors.append(
            T0DraftDescriptor(
                ref_id=ref_id,
                variant_label=stem,
                source_file_stem=stem,
                listed_in_run_json=listed,
                byte_length=byte_length,
                section_count=_section_count(data),
                snippet_preview=_flatten_preview(data),
            )
        )

    return tuple(descriptors)


def _transcript_edit_inventory(dossier_id: str, transcription_id: str) -> TranscriptEditDraftInventory:
    te_dir = transcript_edit_dir(dossier_id, transcription_id)
    working = te_dir / "working.json"
    output = te_dir / "output.json"
    return TranscriptEditDraftInventory(
        working_draft_exists=working.is_file(),
        working_draft_ref=_WORKING_REF if working.is_file() else None,
        output_draft_exists=output.is_file(),
        output_draft_ref=_OUTPUT_REF if output.is_file() else None,
    )


def build_transcript_edit_startup_inventory(
    *,
    dossier_id: str,
    transcription_id: str,
    segment_id: str | None = None,
    run_id: str | None = None,
) -> TranscriptEditStartupInventory:
    """Scan run folder + association metadata; never reads ``head.json`` for the inventory."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    missing: list[MissingResource] = []

    run_dir = transcription_run_dir(dossier_id, transcription_id)
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
            ),
            missing_resources=tuple(missing),
        )

    run_path = run_json_path(dossier_id, transcription_id)
    run_payload = _load_json(run_path)
    if run_payload is None:
        missing.append(
            MissingResource(
                code="run_json_missing_or_unreadable",
                message="run.json missing or not valid JSON.",
                detail=str(run_path),
            )
        )
        completed: list[str] = []
    else:
        if not isinstance(run_payload, dict):
            missing.append(
                MissingResource(
                    code="run_json_invalid_shape",
                    message="run.json root was not an object.",
                    detail=str(run_path),
                )
            )
            completed = []
        else:
            raw_cd = run_payload.get("completed_drafts")
            completed = [str(x) for x in raw_cd] if isinstance(raw_cd, list) else []

    assoc_row, assoc_missing = _load_association_slice(dossier_id, transcription_id)
    missing.extend(assoc_missing)

    raw_dir = raw_drafts_dir(dossier_id, transcription_id)
    t0 = _discover_t0_descriptors(raw_dir, completed)
    if not t0 and raw_dir.is_dir():
        missing.append(
            MissingResource(
                code="no_t0_raw_drafts_found",
                message="No readable T0 JSON drafts found under raw/.",
                detail=str(raw_dir),
            )
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

    fp = _artifact_fingerprint(raw_dir, run_payload if isinstance(run_payload, dict) else None)

    return TranscriptEditStartupInventory(
        scope=TranscriptEditScope(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            segment_id=segment_id,
            run_id=run_id,
        ),
        source_images=images,
        t0_drafts=t0,
        transcript_edit_drafts=_transcript_edit_inventory(dossier_id, transcription_id),
        artifact_fingerprint=fp,
        missing_resources=tuple(missing),
    )
