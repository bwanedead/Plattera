"""Typed startup handoff payload from transcript-edit output (semantic shapes only)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class DeedToIrScope:
    dossier_id: str
    run_id: str | None = None
    workspace_id: str | None = None
    transcription_id: str | None = None


@dataclass(frozen=True)
class TranscriptEditSourceMetadata:
    """Model-facing transcript-edit source identity (no filesystem paths)."""

    loaded_source_label: str = "transcript_edit_output"
    source_revision_ref: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class DeedToIrStartupHandoff:
    """Mechanical summary of transcript-edit final output lanes for deed-to-IR orientation."""

    scope: DeedToIrScope
    source: TranscriptEditSourceMetadata
    normalized_or_mapping_transcript: str | None = None
    source_transcript_verbatim: str | None = None
    issues: tuple[dict[str, Any], ...] = ()
    hitl_decisions: tuple[dict[str, Any], ...] = ()
    parcel_metadata: dict[str, Any] = field(default_factory=dict)
    evidence_refs: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    excerpts: dict[str, str | None] = field(default_factory=dict)


def startup_handoff_from_loader_dict(
    *,
    scope: DeedToIrScope,
    loaded: dict[str, Any],
) -> DeedToIrStartupHandoff:
    """Map mechanical loader output into domain payload (field copy only)."""
    source_raw = loaded.get("source") if isinstance(loaded.get("source"), dict) else {}
    counts_raw = loaded.get("counts") if isinstance(loaded.get("counts"), dict) else {}
    excerpts_raw = loaded.get("excerpts") if isinstance(loaded.get("excerpts"), dict) else {}
    parcel_raw = loaded.get("parcel_metadata") if isinstance(loaded.get("parcel_metadata"), dict) else {}

    return DeedToIrStartupHandoff(
        scope=scope,
        source=TranscriptEditSourceMetadata(
            loaded_source_label=_opt_str(source_raw.get("loaded_source_label"))
            or "transcript_edit_output",
            source_revision_ref=_opt_str(source_raw.get("source_revision_ref")),
            published_at=_opt_str(source_raw.get("published_at")),
        ),
        normalized_or_mapping_transcript=_opt_str(loaded.get("normalized_or_mapping_transcript")),
        source_transcript_verbatim=_opt_str(loaded.get("source_transcript_verbatim")),
        issues=tuple(row for row in _list_dicts(loaded.get("issues"))),
        hitl_decisions=tuple(row for row in _list_dicts(loaded.get("hitl_decisions"))),
        parcel_metadata=dict(parcel_raw),
        evidence_refs=tuple(_str_list(loaded.get("evidence_refs"))),
        counts={str(k): int(v) for k, v in counts_raw.items() if isinstance(v, int)},
        excerpts={
            str(k): (_opt_str(v) if v is not None else None)
            for k, v in excerpts_raw.items()
        },
    )


def _opt_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _list_dicts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(row) for row in value if isinstance(row, dict)]


def _str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
    return out
