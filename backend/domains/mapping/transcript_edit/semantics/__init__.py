"""Transcript-edit closure and handoff meaning (not runtime stop logic)."""

from .closure import (
    TranscriptEditClosureSemantics,
    build_transcript_edit_closure_policy,
    transcript_edit_closure_semantics,
)
from .handoff import TranscriptEditHandoffSemantics, transcript_edit_handoff_semantics

__all__ = [
    "TranscriptEditClosureSemantics",
    "build_transcript_edit_closure_policy",
    "TranscriptEditHandoffSemantics",
    "transcript_edit_closure_semantics",
    "transcript_edit_handoff_semantics",
]
