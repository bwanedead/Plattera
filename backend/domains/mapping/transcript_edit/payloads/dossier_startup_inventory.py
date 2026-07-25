"""Dossier-scoped transcript-edit startup inventory contracts (semantic shapes only)."""

from __future__ import annotations

from dataclasses import dataclass

from domains.mapping.transcript_edit.payloads.startup_inventory import MissingResource


@dataclass(frozen=True)
class DossierTranscriptEditScope:
    dossier_id: str
    run_id: str | None = None
    workspace_id: str | None = None


@dataclass(frozen=True)
class DossierTranscriptRunInventory:
    transcription_id: str
    position: int | None
    source_image_refs: tuple[str, ...]
    t0_draft_refs: tuple[str, ...]
    working_draft_ref: str | None
    output_draft_ref: str | None
    artifact_fingerprint: str | None
    missing_resources: tuple[MissingResource, ...]


@dataclass(frozen=True)
class DossierTranscriptSegmentInventory:
    segment_id: str
    position: int
    previous_segment_id: str | None
    next_segment_id: str | None
    runs: tuple[DossierTranscriptRunInventory, ...]


@dataclass(frozen=True)
class DossierTopologyDiagnostic:
    code: str
    segment_id: str | None = None
    transcription_id: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class DossierTranscriptEditStartupInventory:
    scope: DossierTranscriptEditScope
    topology_fingerprint: str
    segment_count: int
    segments: tuple[DossierTranscriptSegmentInventory, ...]
    topology_diagnostics: tuple[DossierTopologyDiagnostic, ...]
