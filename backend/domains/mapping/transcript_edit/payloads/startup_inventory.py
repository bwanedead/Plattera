"""Ref-first startup inventory for transcript-edit first model contact (semantic shapes only)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TranscriptEditScope:
    """Dossier / transcription scope for the run (no storage paths)."""

    dossier_id: str
    transcription_id: str
    segment_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class SourceImageRefDescriptor:
    """Source imagery available for grounding; refs + metadata only (no blobs)."""

    ref_id: str
    role: str
    basename: str | None = None
    storage_hint: str | None = None


@dataclass(frozen=True)
class T0DraftDescriptor:
    """One peer T0 raw draft; equal standing—no ranking or “best” label."""

    ref_id: str
    variant_label: str
    source_file_stem: str
    listed_in_run_json: bool = False
    byte_length: int | None = None
    section_count: int | None = None
    snippet_preview: str | None = None


@dataclass(frozen=True)
class TranscriptEditDraftInventory:
    """Authored transcript-edit artifacts (separate from T0 peer drafts)."""

    working_draft_exists: bool = False
    working_draft_ref: str | None = None
    output_draft_exists: bool = False
    output_draft_ref: str | None = None


@dataclass(frozen=True)
class MissingResource:
    """Structured gap when dossier/run data is incomplete (not an invented fallback)."""

    code: str
    message: str
    detail: str | None = None


@dataclass(frozen=True)
class TranscriptEditStartupInventory:
    """Resource inventory for first contact: what exists, not what to do next."""

    scope: TranscriptEditScope
    source_images: tuple[SourceImageRefDescriptor, ...] = ()
    t0_drafts: tuple[T0DraftDescriptor, ...] = ()
    transcript_edit_drafts: TranscriptEditDraftInventory = field(
        default_factory=TranscriptEditDraftInventory
    )
    artifact_fingerprint: str | None = None
    missing_resources: tuple[MissingResource, ...] = ()
