"""Transcript-edit semantic state contracts and projection."""

from .contracts import (
    CandidateRepair,
    DownstreamReadinessPosture,
    EvidencePosture,
    FinalSelectionPosture,
    TranscriptAmbiguity,
    TranscriptDefect,
    TranscriptEditSemanticState,
    VerificationPosture,
)
from .projection import TranscriptEditProjectedView, project_transcript_edit_view

__all__ = [
    "CandidateRepair",
    "DownstreamReadinessPosture",
    "EvidencePosture",
    "FinalSelectionPosture",
    "TranscriptAmbiguity",
    "TranscriptDefect",
    "TranscriptEditProjectedView",
    "TranscriptEditSemanticState",
    "VerificationPosture",
    "project_transcript_edit_view",
]
