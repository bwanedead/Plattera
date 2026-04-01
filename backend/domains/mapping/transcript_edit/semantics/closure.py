"""What 'done enough' means for transcript edit—semantic only; harness decides stopping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEditClosureSemantics:
    """Domain-owned completion criteria phrasing for prompts and review—not executable law."""

    summary: str
    sufficient_when: tuple[str, ...]
    must_remain_explicit_if_unresolved: tuple[str, ...]
    anti_patterns: tuple[str, ...]


def transcript_edit_closure_semantics() -> TranscriptEditClosureSemantics:
    return TranscriptEditClosureSemantics(
        summary=(
            "Closure means the active transcript issues are either resolved with evidence-grounded text "
            "or explicitly documented as still blocked, with no silent ambiguity carried forward."
        ),
        sufficient_when=(
            "Each prioritized ambiguity or defect has a recorded disposition: fixed, accepted with rationale, or deferred with explicit blockers.",
            "Verification posture states why the current text matches image and draft evidence, or what evidence is still missing.",
            "Repairs that change meaning are tied to image or draft evidence—not unsupported rewrites.",
            "If finals or heads are in scope, their posture is coherent: either selected with rationale or explicitly not ready.",
        ),
        must_remain_explicit_if_unresolved=(
            "Residual ambiguities that could change boundary or corner interpretation in mapping.",
            "Known OCR or alignment failures that could distort bearings, curves, or calls.",
            "Conflicting drafts where no evidence-backed choice was made.",
            "Any dependency on human verification that has not returned.",
        ),
        anti_patterns=(
            "Treating stylistic polish as closure while geometrically material text is still uncertain.",
            "Closing because of iteration limits rather than evidence state.",
            "Declaring verification without tying claims to image or draft refs.",
        ),
    )
