"""Transcript-edit domain edge adapter for generic harness composition surfaces."""

from .adapter import TranscriptEditRuntimeAdapter, build_transcript_edit_runtime_adapter
from .composition import (
    TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID,
    build_transcript_edit_turn_surface,
    build_transcript_edit_tool_bindings,
)

__all__ = [
    "TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID",
    "TranscriptEditRuntimeAdapter",
    "build_transcript_edit_runtime_adapter",
    "build_transcript_edit_turn_surface",
    "build_transcript_edit_tool_bindings",
]
