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
class TranscriptEditAuthoredDraftPosture:
    """Posture for the agent-authored transcript-edit working/output draft (not T0 peer selection)."""

    narrative: str
    working_draft_ref: str | None = None
    output_draft_ref: str | None = None


@dataclass(frozen=True)
class DownstreamReadinessPosture:
    """Whether transcript state is adequate to enter mapping-centric work."""

    narrative: str
    ready_for_mapping: bool = False
    explicit_blockers: tuple[str, ...] = ()


@dataclass(frozen=True)
class TranscriptEditClosureLayerPosture:
    """Explicit authored posture for one transcript-edit closure layer."""

    layer_id: str
    title: str
    status: str
    summary: str
    determination: str | None = None
    mapping_blocking: bool | None = None
    requires_hitl: bool = False
    no_further_progress: bool = False
    evidence_refs: tuple[str, ...] = ()
    verification_basis: str | None = None
    next_needed_step: str | None = None


@dataclass(frozen=True)
class TranscriptEditClosureLedger:
    """Holistic transcript-edit closure posture across the four domain layers."""

    overall_status: str | None = None
    summary: str | None = None
    publish_ready: bool = False
    complete_ready: bool = False
    requires_hitl: bool = False
    no_further_progress: bool = False
    layer_1_delta_convergence: TranscriptEditClosureLayerPosture | None = None
    layer_2_intrinsic_source_integrity: TranscriptEditClosureLayerPosture | None = None
    layer_3_external_dependency_completeness: TranscriptEditClosureLayerPosture | None = None
    layer_4_mapping_blocking_relevance: TranscriptEditClosureLayerPosture | None = None


@dataclass(frozen=True)
class TranscriptEditSemanticState:
    """Single bundle for domain-local semantic truth (authoritative for this pack)."""

    ambiguities: tuple[TranscriptAmbiguity, ...] = ()
    defects: tuple[TranscriptDefect, ...] = ()
    evidence: EvidencePosture | None = None
    candidate_repairs: tuple[CandidateRepair, ...] = ()
    verification: VerificationPosture | None = None
    authored_draft_posture: TranscriptEditAuthoredDraftPosture | None = None
    downstream: DownstreamReadinessPosture | None = None
    closure: TranscriptEditClosureLedger | None = None
    human_feedback_notes: tuple[str, ...] = ()
