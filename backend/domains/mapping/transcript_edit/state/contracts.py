"""Canonical semantic state shapes for transcript edit (truth models for the domain)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptAmbiguity:
    """Unresolved meaning or competing readings in transcript text."""

    issue_id: str
    summary: str
    segment_ref: str | None = None
    run_ref: str | None = None
    span_hint: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class TranscriptDefect:
    """A concrete flaw (OCR glitch, merge error, illegal span, etc.)."""

    defect_id: str
    kind: str
    description: str
    segment_ref: str | None = None
    run_ref: str | None = None


@dataclass(frozen=True)
class EvidencePosture:
    """Whether available evidence supports or undermines current transcript claims."""

    narrative: str
    image_refs: tuple[str, ...] = ()
    draft_refs: tuple[str, ...] = ()
    sufficiency_summary: str | None = None


@dataclass(frozen=True)
class CandidateRepair:
    """A proposed evidence-grounded change—not yet committed as system truth."""

    repair_id: str
    rationale: str
    proposed_text: str | None = None
    target_draft_ref: str | None = None
    target_segment_ref: str | None = None


@dataclass(frozen=True)
class VerificationPosture:
    """Agent/human judgment about trust in the current transcript state."""

    narrative: str
    blocking_issues: tuple[str, ...] = ()
    needs_more_image_evidence: bool = False
    needs_more_draft_evidence: bool = False
    needs_human_input: bool = False


@dataclass(frozen=True)
class FinalSelectionPosture:
    """Readiness for pinned segment finals vs authored transcript-edit output (not persistence)."""

    narrative: str
    selected_final_ref: str | None = None
    authored_transcript_edit_ref: str | None = None
    conflicts_remain: bool = False


@dataclass(frozen=True)
class DownstreamReadinessPosture:
    """Whether transcript state is adequate to enter mapping-centric work."""

    narrative: str
    ready_for_mapping: bool = False
    explicit_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranscriptEditSemanticState:
    """Single bundle for domain-local semantic truth (authoritative for this pack)."""

    ambiguities: tuple[TranscriptAmbiguity, ...] = ()
    defects: tuple[TranscriptDefect, ...] = ()
    evidence: EvidencePosture | None = None
    candidate_repairs: tuple[CandidateRepair, ...] = ()
    verification: VerificationPosture | None = None
    final_selection: FinalSelectionPosture | None = None
    downstream: DownstreamReadinessPosture | None = None
    human_feedback_notes: tuple[str, ...] = ()
