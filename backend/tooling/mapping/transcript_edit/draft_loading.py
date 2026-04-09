"""Hydrate T0 and transcript-edit draft artifacts by ref (no ranking or merge)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .draft_persistence import parse_working_revision_ref, resolve_workspace_key
from .paths import (
    UnsafeArtifactPathSegmentError,
    raw_drafts_dir,
    require_safe_workspace_relative_path,
    transcript_edit_latest_pointer_path,
    transcript_edit_output_path,
    transcript_edit_revision_path,
    transcript_edit_workspace_root,
)
from .startup_inventory import _OUTPUT_REF, _T0_REF_PREFIX, _WORKING_REF

_DRAFT_ALIAS_RE = re.compile(r"^draft_(?P<ordinal>[1-9]\d*)$", re.IGNORECASE)


def _safe_stem_from_t0_ref(ref_id: str) -> str | None:
    rid = str(ref_id).strip()
    if not rid.startswith(_T0_REF_PREFIX):
        return None
    stem = rid[len(_T0_REF_PREFIX) :].strip()
    if not stem or "/" in stem or "\\" in stem or stem.startswith("."):
        return None
    if ".." in stem:
        return None
    return stem


def _ordered_peer_stems(raw_dir: Path, *, transcription_id: str, run_payload: dict[str, Any] | None) -> tuple[str, ...]:
    completed: list[str] = []
    completed_is_authoritative = False
    if isinstance(run_payload, dict) and isinstance(run_payload.get("completed_drafts"), list):
        completed = [str(x).strip() for x in run_payload.get("completed_drafts") or [] if str(x).strip()]
        completed_is_authoritative = len(completed) > 0

    if completed_is_authoritative:
        out: list[str] = []
        for stem in completed:
            if stem == transcription_id:
                continue
            if (raw_dir / f"{stem}.json").is_file():
                out.append(stem)
        return tuple(out)

    stems: list[str] = []
    for path in sorted(raw_dir.glob("*.json")):
        if not path.is_file():
            continue
        stem = path.stem
        if stem == transcription_id:
            continue
        stems.append(stem)
    return tuple(stems)


def _resolve_source_stem_for_ref(
    *,
    ref_id: str,
    raw_dir: Path,
    dossier_id: str,
    transcription_id: str,
) -> tuple[str | None, dict[str, Any] | None]:
    stem = _safe_stem_from_t0_ref(ref_id)
    if stem is None:
        return None, {"ref_id": ref_id, "code": "invalid_ref", "message": "Expected t0:raw:draft_N alias or t0:raw:<file_stem>."}
    if stem == transcription_id:
        return None, {
            "ref_id": ref_id,
            "code": "legacy_pointer_alias",
            "message": "This stem is the legacy raw pointer copy, not a peer T0 pass; use peer draft refs.",
        }

    alias = _DRAFT_ALIAS_RE.match(stem)
    if alias is None:
        return stem, None

    run_payload: dict[str, Any] | None = None
    try:
        from .paths import run_json_path

        run_path = run_json_path(dossier_id, transcription_id)
        if run_path.is_file():
            loaded = json.loads(run_path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                run_payload = loaded
    except Exception:
        run_payload = None

    ordered = _ordered_peer_stems(raw_dir, transcription_id=transcription_id, run_payload=run_payload)
    ordinal = int(alias.group("ordinal"))
    if ordinal > len(ordered):
        return None, {
            "ref_id": ref_id,
            "code": "not_found",
            "message": f"Peer draft alias draft_{ordinal} is out of range for this transcription.",
        }
    return ordered[ordinal - 1], None


@dataclass(frozen=True)
class HydratedT0Draft:
    ref_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HydrateT0DraftsResult:
    drafts: tuple[HydratedT0Draft, ...]
    errors: tuple[dict[str, Any], ...]
    cap_exceeded: bool = False
    omitted_ref_ids: tuple[str, ...] = ()
    max_refs_applied: int = 8


def _draft_text(data: dict[str, Any]) -> str:
    parts: list[str] = []
    for sec in data.get("sections") or []:
        if isinstance(sec, dict) and sec.get("body"):
            parts.append(str(sec["body"]))
    if parts:
        return "\n\n".join(parts).strip()
    for key in ("text", "transcript", "body"):
        if data.get(key):
            return str(data[key]).strip()
    return ""


def hydrate_t0_draft_refs(
    *,
    dossier_id: str,
    transcription_id: str,
    ref_ids: list[str],
    max_refs: int = 8,
) -> HydrateT0DraftsResult:
    """Load full text for one or many ``t0:raw:<stem>`` refs; cap is explicit when partial."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    cap = max(1, min(int(max_refs), 32))
    all_refs = [str(r).strip() for r in ref_ids if str(r).strip()]
    cap_exceeded = len(all_refs) > cap
    omitted = tuple(all_refs[cap:]) if cap_exceeded else ()
    to_process = all_refs[:cap]

    drafts: list[HydratedT0Draft] = []
    errors: list[dict[str, Any]] = []
    try:
        raw_dir = raw_drafts_dir(dossier_id, transcription_id)
    except UnsafeArtifactPathSegmentError as exc:
        return HydrateT0DraftsResult(
            drafts=tuple(),
            errors=(
                {
                    "code": "invalid_scope_path",
                    "message": str(exc),
                },
            ),
            cap_exceeded=False,
            omitted_ref_ids=tuple(),
            max_refs_applied=cap,
        )

    if cap_exceeded:
        errors.append(
            {
                "code": "cap_exceeded",
                "message": f"Requested {len(all_refs)} refs; max_refs={cap}. Only the first {cap} were hydrated.",
                "requested_count": len(all_refs),
                "max_refs": cap,
                "omitted_ref_ids": list(omitted),
            }
        )

    for ref_id in to_process:
        stem, err = _resolve_source_stem_for_ref(
            ref_id=ref_id,
            raw_dir=raw_dir,
            dossier_id=dossier_id,
            transcription_id=transcription_id,
        )
        if err is not None:
            errors.append(err)
            continue
        path = raw_dir / f"{stem}.json"
        if not path.is_file():
            errors.append({"ref_id": ref_id, "code": "not_found", "message": str(path)})
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            errors.append({"ref_id": ref_id, "code": "read_error", "message": str(exc)})
            continue
        if not isinstance(data, dict):
            errors.append({"ref_id": ref_id, "code": "invalid_json_shape", "message": "Expected object root."})
            continue
        text = _draft_text(data)
        meta: dict[str, Any] = {
            "path": str(path.resolve()),
            "source_file_stem": stem,
            "section_count": len(data["sections"]) if isinstance(data.get("sections"), list) else None,
        }
        drafts.append(HydratedT0Draft(ref_id=ref_id, text=text, metadata=meta))

    return HydrateT0DraftsResult(
        drafts=tuple(drafts),
        errors=tuple(errors),
        cap_exceeded=cap_exceeded,
        omitted_ref_ids=omitted,
        max_refs_applied=cap,
    )


def hydrate_transcript_edit_working_draft(
    *,
    dossier_id: str,
    transcription_id: str,
    ref_id: str,
    workspace_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Load transcript-edit workspace artifact by ref (latest working, specific rev, or published output)."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    rid = str(ref_id).strip()
    ws = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not ws:
        return {
            "status": "error",
            "code": "workspace_required",
            "message": "Provide workspace_id or run_id to resolve transcript_edit artifact paths.",
        }

    path: Path | None = None
    try:
        if rid == _OUTPUT_REF:
            path = transcript_edit_output_path(dossier_id, transcription_id, ws)
        elif rid == _WORKING_REF:
            lp = transcript_edit_latest_pointer_path(dossier_id, transcription_id, ws)
            if not lp.is_file():
                return {"status": "error", "code": "not_found", "message": str(lp)}
            try:
                ptr = json.loads(lp.read_text(encoding="utf-8"))
            except Exception as exc:
                return {"status": "error", "code": "read_error", "message": str(exc)}
            if not isinstance(ptr, dict) or not ptr.get("relative_path"):
                return {
                    "status": "error",
                    "code": "invalid_latest_pointer",
                    "message": str(lp),
                }
            rel = require_safe_workspace_relative_path(str(ptr["relative_path"]))
            path = transcript_edit_workspace_root(dossier_id, transcription_id, ws) / rel
        else:
            rev_digits = parse_working_revision_ref(rid)
            if rev_digits:
                path = transcript_edit_revision_path(dossier_id, transcription_id, ws, rev_digits)
            else:
                return {
                    "status": "error",
                    "code": "invalid_ref",
                    "message": "Expected transcript_edit:working, transcript_edit:output, or transcript_edit:working:rev:NNNN.",
                }
    except UnsafeArtifactPathSegmentError as exc:
        return {
            "status": "error",
            "code": "invalid_scope_path",
            "message": str(exc),
        }

    assert path is not None
    if not path.is_file():
        return {"status": "error", "code": "not_found", "message": str(path)}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "error", "code": "read_error", "message": str(exc)}

    return {
        "status": "ok",
        "ref_id": rid,
        "path": str(path.resolve()),
        "payload": data,
    }
