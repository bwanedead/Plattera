"""Readiness to leave transcript edit for downstream mapping—semantic contract only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEditHandoffSemantics:
    """What downstream mapping is allowed to assume—documentation for agents, not wiring."""

    summary: str
    ready_when: tuple[str, ...]
    artifact_expectations: tuple[str, ...]
    should_not_hand_off_yet: tuple[str, ...]


def transcript_edit_handoff_semantics() -> TranscriptEditHandoffSemantics:
    return TranscriptEditHandoffSemantics(
        summary=(
            "Handoff means mapping-oriented consumers can trust the transcript snapshot: scope is clear, "
            "the authored transcript-edit output reflects evidence, and remaining risk is labeled—not hidden."
        ),
        ready_when=(
            "Downstream readiness posture explicitly affirms trust for mapping or documents blockers.",
            "Authored transcript-edit working/output draft and hydrated peer refs align with the verification narrative.",
            "Any human-input dependencies are either satisfied or ticketed with refs.",
        ),
        artifact_expectations=(
            "Refs for dossier, segment, run, t0 peers, and transcript-edit drafts as required by tooling.",
            "Short human-readable notes capturing residual risk acceptable to mapping.",
            "Evidence refs (image crops, draft ids) for non-obvious repairs that affect geometry-bearing language.",
        ),
        should_not_hand_off_yet=(
            "Material ambiguity on geometry-bearing or operative language without disposition.",
            "Known mismatch between transcript span and imagery that changes legal reading.",
            "Claiming handoff while the authored transcript-edit draft is missing or inconsistent with cited evidence.",
        ),
    )
