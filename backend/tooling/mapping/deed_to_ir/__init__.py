"""Deed-to-IR tooling (Brief A: transcript-edit output loading only)."""

from .transcript_handoff_loading import (
    LOADED_SOURCE_LABEL,
    TranscriptHandoffLoadError,
    load_transcript_edit_output_handoff,
)

__all__ = [
    "LOADED_SOURCE_LABEL",
    "TranscriptHandoffLoadError",
    "load_transcript_edit_output_handoff",
]
