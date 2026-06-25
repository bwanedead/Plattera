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
    resolution_state_ref: str | None = None
    resolution_state_snapshot: dict[str, Any] | None = None
    resolution_state_counts: dict[str, int] = field(default_factory=dict)
    resolution_state_summary: tuple[dict[str, Any], ...] = ()
    inherited_handoff_conditions: dict[str, Any] = field(default_factory=dict)
