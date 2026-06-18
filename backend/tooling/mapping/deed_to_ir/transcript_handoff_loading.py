"""Mechanical loading of transcript-edit output for deed-to-IR startup handoff.

Copies fields from published output JSON without semantic inference or mutation.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class TranscriptHandoffLoadError(ValueError):
    """Raised when output JSON cannot be read or lacks required mechanical shape."""


MAX_EXCERPT_CHARS = 600
LOADED_SOURCE_LABEL = "transcript_edit_output"


def load_transcript_edit_output_handoff(*, output_path: str | Path) -> dict[str, Any]:
    """Load and summarize transcript-edit output for deed-to-IR startup (copy-only)."""
    path = Path(output_path)
    if not path.is_file():
        raise TranscriptHandoffLoadError(f"transcript_edit_output_not_found:{path}")

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TranscriptHandoffLoadError(f"transcript_edit_output_unreadable:{path}") from exc

    if not isinstance(raw, Mapping):
        raise TranscriptHandoffLoadError("transcript_edit_output_not_object")

    snapshot = raw.get("revision_snapshot")
    if not isinstance(snapshot, Mapping):
        raise TranscriptHandoffLoadError("transcript_edit_output_missing_revision_snapshot")

    payload = snapshot.get("payload")
    if not isinstance(payload, Mapping):
        raise TranscriptHandoffLoadError("transcript_edit_output_missing_payload")

    normalized = _optional_text(payload.get("normalized_or_mapping_transcript"))
    verbatim = _optional_text(payload.get("source_transcript_verbatim"))
    issues = _copy_list(payload.get("issues"))
    hitl = _copy_list(payload.get("hitl_decisions"))
    parcel_metadata = _copy_mapping(payload.get("parcel_metadata"))
    evidence_refs = _bounded_str_list(payload.get("evidence_refs"))

    return {
        "source": {
            "loaded_source_label": LOADED_SOURCE_LABEL,
            "source_revision_ref": _optional_text(raw.get("source_revision_ref"))
            or _optional_text(snapshot.get("ref_id")),
            "published_at": _optional_text(raw.get("published_at")),
        },
        "normalized_or_mapping_transcript": normalized,
        "source_transcript_verbatim": verbatim,
        "issues": issues,
        "hitl_decisions": hitl,
        "parcel_metadata": parcel_metadata,
        "evidence_refs": evidence_refs,
        "counts": {
            "issues": len(issues),
            "hitl_decisions": len(hitl),
            "parcels": len(_parcel_rows(parcel_metadata)),
            "evidence_refs": len(evidence_refs),
        },
        "excerpts": {
            "normalized_or_mapping_transcript": _excerpt(normalized),
            "source_transcript_verbatim": _excerpt(verbatim),
        },
    }


def _parcel_rows(parcel_metadata: Mapping[str, Any]) -> list[Any]:
    parcels = parcel_metadata.get("parcels")
    return list(parcels) if isinstance(parcels, list) else []


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _copy_list(value: Any) -> list[Any]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, (dict, list, str, int, float, bool)) or item is None]


def _copy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)


def _bounded_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if not isinstance(entry, str):
            continue
        text = entry.strip()
        if text and text not in out:
            out.append(text)
    return out


def _excerpt(text: str | None) -> str | None:
    if not text:
        return None
    if len(text) <= MAX_EXCERPT_CHARS:
        return text
    return text[: MAX_EXCERPT_CHARS - 1].rstrip() + "…"
