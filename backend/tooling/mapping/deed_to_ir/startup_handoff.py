"""Mechanical assembly of deed-to-IR startup handoff from loader + launch context."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from domains.mapping.deed_to_ir.payloads import (
    DeedToIrScope,
    DeedToIrStartupHandoff,
    TranscriptEditSourceMetadata,
)

from .inherited_handoff_projection import build_inherited_handoff_conditions
from .resolution_state_projection import (
    ResolutionStateHandoffError,
    mechanical_resolution_state_snapshot,
    resolution_state_counts,
    resolution_state_startup_summary,
    validate_resolution_state_handoff,
)
from .transcript_handoff_loading import load_transcript_edit_output_handoff


def build_deed_to_ir_startup_handoff(
    *,
    scope: DeedToIrScope,
    transcript_edit_output_path: str,
    resolution_state_ref: str | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
) -> DeedToIrStartupHandoff:
    """Load transcript-edit output and merge explicit resolution-state snapshot (copy-only)."""
    loaded = load_transcript_edit_output_handoff(output_path=transcript_edit_output_path)
    return startup_handoff_from_loader_dict(
        scope=scope,
        loaded=loaded,
        resolution_state_ref=resolution_state_ref,
        resolution_state_snapshot=resolution_state_snapshot,
    )


def startup_handoff_from_loader_dict(
    *,
    scope: DeedToIrScope,
    loaded: dict[str, Any],
    resolution_state_ref: str | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
) -> DeedToIrStartupHandoff:
    """Map mechanical loader output into domain payload (field copy only)."""
    ref_text = _opt_str(resolution_state_ref)
    validate_resolution_state_handoff(
        resolution_state_ref=ref_text,
        resolution_state_snapshot=resolution_state_snapshot,
    )
    source_raw = loaded.get("source") if isinstance(loaded.get("source"), dict) else {}
    counts_raw = loaded.get("counts") if isinstance(loaded.get("counts"), dict) else {}
    excerpts_raw = loaded.get("excerpts") if isinstance(loaded.get("excerpts"), dict) else {}
    parcel_raw = loaded.get("parcel_metadata") if isinstance(loaded.get("parcel_metadata"), dict) else {}

    counts = {str(k): int(v) for k, v in counts_raw.items() if isinstance(v, int)}
    snapshot = mechanical_resolution_state_snapshot(resolution_state_snapshot)
    rs_counts = resolution_state_counts(snapshot)
    if snapshot is not None:
        counts = {**counts, **{f"resolution_{k}": v for k, v in rs_counts.items()}}

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
        counts=counts,
        excerpts={
            str(k): (_opt_str(v) if v is not None else None)
            for k, v in excerpts_raw.items()
        },
        resolution_state_ref=ref_text,
        resolution_state_snapshot=snapshot,
        resolution_state_counts=rs_counts,
        resolution_state_summary=tuple(resolution_state_startup_summary(snapshot)),
        inherited_handoff_conditions=build_inherited_handoff_conditions(
            source=source_raw,
            parcel_metadata=parcel_raw,
            issues=_list_dicts(loaded.get("issues")),
            hitl_decisions=_list_dicts(loaded.get("hitl_decisions")),
            evidence_refs=_str_list(loaded.get("evidence_refs")),
            resolution_state_ref=ref_text,
            normalized_or_mapping_transcript=_opt_str(loaded.get("normalized_or_mapping_transcript")),
            source_transcript_verbatim=_opt_str(loaded.get("source_transcript_verbatim")),
            excerpts=excerpts_raw,
        ),
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
