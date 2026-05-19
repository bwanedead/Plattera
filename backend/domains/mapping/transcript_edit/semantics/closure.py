"""What 'done enough' means for transcript edit—semantic only; harness decides stopping."""

from __future__ import annotations

from dataclasses import dataclass

from domains.closure_policy import ClosureDimensionStandard, DomainClosurePolicy


@dataclass(frozen=True)
class TranscriptEditClosureSemantics:
    """Domain-owned completion criteria phrasing for prompts and review—not executable law."""

    summary: str
    sufficient_when: tuple[str, ...]
    must_remain_explicit_if_unresolved: tuple[str, ...]
    anti_patterns: tuple[str, ...]


def build_transcript_edit_closure_policy() -> DomainClosurePolicy:
    return DomainClosurePolicy(
        hard_enforced=True,
        enforce_on_publish=True,
        enforce_on_complete=True,
        save_action_ids=("save_workspace_artifact", "copy_forward_save_workspace_artifact"),
        publish_action_ids=("publish_workspace_artifact",),
        minimum_resolution_items_for_save=1,
        minimum_resolution_items_for_wait=1,
        minimum_resolution_items_for_publish=1,
        minimum_resolution_items_for_complete=1,
        required_dimension_ids=(
            "layer_1_delta_convergence",
            "layer_2_intrinsic_source_integrity",
            "layer_3_external_dependency_completeness",
            "layer_4_mapping_blocking_relevance",
        ),
        standards=(
            ClosureDimensionStandard(
                dimension_id="layer_1_delta_convergence",
                title="Layer 1 — Delta convergence",
                question="Has the transcript been brought into maximal agreement with the source evidence available here?",
                guidance="Use this layer to record whether transcript/source deltas are actually resolved.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_2_intrinsic_source_integrity",
                title="Layer 2 — Intrinsic source integrity",
                question="Assuming the transcript is faithful, does the source itself still contain a contradiction, defect, or unresolved internal inconsistency?",
                guidance="Use this layer to keep source defects explicit instead of collapsing them into transcript edits.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_3_external_dependency_completeness",
                title="Layer 3 — External dependency completeness",
                question="Is any required meaning, reference, or operative detail missing from the current source set and only obtainable from outside material?",
                guidance="Use this layer when closure depends on another document, exhibit, retrieval result, or human-provided material.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_4_mapping_blocking_relevance",
                title="Layer 4 — Mapping-blocking relevance",
                question="Do the remaining unresolved issues actually block downstream mapping, or are they explicitly non-blocking?",
                guidance="Use this layer to decide whether unresolved issues prevent publish/complete or merely remain caveated.",
            ),
        ),
    )


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
            "Authored transcript-edit working/output posture is coherent: either aligned with evidence or explicitly not ready.",
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
