"""Hydrate T0 and transcript-edit draft artifacts by ref (no ranking or merge)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .paths import raw_drafts_dir, transcript_edit_dir
from .startup_inventory import _OUTPUT_REF, _T0_REF_PREFIX, _WORKING_REF


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


@dataclass(frozen=True)
class HydratedT0Draft:
    ref_id: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class HydrateT0DraftsResult:
    drafts: tuple[HydratedT0Draft, ...]
    errors: tuple[dict[str, Any], ...]


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
    """Load full text for one or many ``t0:raw:<stem>`` refs; cap enforced; no merge."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    cap = max(1, min(int(max_refs), 32))
    trimmed = [str(r).strip() for r in ref_ids if str(r).strip()][:cap]

    drafts: list[HydratedT0Draft] = []
    errors: list[dict[str, Any]] = []
    raw_dir = raw_drafts_dir(dossier_id, transcription_id)

    for ref_id in trimmed:
        stem = _safe_stem_from_t0_ref(ref_id)
        if stem is None:
            errors.append({"ref_id": ref_id, "code": "invalid_ref", "message": "Expected t0:raw:<file_stem>."})
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

    return HydrateT0DraftsResult(drafts=tuple(drafts), errors=tuple(errors))


def hydrate_transcript_edit_working_draft(
    *,
    dossier_id: str,
    transcription_id: str,
    ref_id: str,
) -> dict[str, Any]:
    """Load authored transcript-edit artifact by ref (``transcript_edit:working`` or ``:output``)."""
    dossier_id = str(dossier_id).strip()
    transcription_id = str(transcription_id).strip()
    rid = str(ref_id).strip()
    te_dir = transcript_edit_dir(dossier_id, transcription_id)
    if rid == _WORKING_REF:
        path: Path = te_dir / "working.json"
    elif rid == _OUTPUT_REF:
        path = te_dir / "output.json"
    else:
        return {"status": "error", "code": "invalid_ref", "message": "Expected transcript_edit:working or transcript_edit:output."}

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
