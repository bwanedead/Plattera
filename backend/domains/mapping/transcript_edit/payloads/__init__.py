"""Model-facing payload contracts for transcript_edit (no persistence, no dossier I/O)."""

from .startup_inventory import (
    MissingResource,
    SourceImageRefDescriptor,
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)

__all__ = [
    "MissingResource",
    "SourceImageRefDescriptor",
    "T0DraftDescriptor",
    "TranscriptEditDraftInventory",
    "TranscriptEditScope",
    "TranscriptEditStartupInventory",
]
