"""What 'done enough' means for deed-to-IR — semantic only; harness decides stopping."""

from __future__ import annotations

from dataclasses import dataclass

from domains.closure_policy import ClosureDimensionStandard, DomainClosurePolicy


@dataclass(frozen=True)
class DeedToIrClosureSemantics:
    summary: str
    sufficient_when: tuple[str, ...]
    must_remain_explicit_if_unresolved: tuple[str, ...]
    anti_patterns: tuple[str, ...]


def build_deed_to_ir_closure_policy() -> DomainClosurePolicy:
    """Soft closure policy skeleton; hard enforcement arrives with artifact tools."""
    return DomainClosurePolicy(
        hard_enforced=False,
        enforce_on_publish=False,
        enforce_on_complete=False,
        save_action_ids=(),
        publish_action_ids=(),
        minimum_resolution_items_for_save=0,
        minimum_resolution_items_for_wait=0,
        minimum_resolution_items_for_publish=0,
        minimum_resolution_items_for_complete=0,
        required_dimension_ids=(
            "layer_1_deed_meaning_to_ir_fidelity",
            "layer_2_ir_geometry_integrity",
            "layer_3_external_dependency_representability_completeness",
            "layer_4_map_handoffability_scoped_completion",
        ),
        required_output_ref_for_complete=None,
        standards=(
            ClosureDimensionStandard(
                dimension_id="layer_1_deed_meaning_to_ir_fidelity",
                title="Layer 1 — Deed meaning to IR fidelity",
                question="Has the deed meaning for the mappable scope been represented in feature-graph IR as faithfully and completely as current information allows?",
                guidance=(
                    "Use transcript-edit handoff as the substrate, but record diagnosis and repair "
                    "when downstream IR or map sanity exposes a real upstream issue."
                ),
            ),
            ClosureDimensionStandard(
                dimension_id="layer_2_ir_geometry_integrity",
                title="Layer 2 — IR and geometry integrity",
                question="Assuming the IR expresses the intended deed meaning, is the IR internally coherent and does its compiled/rendered geometry make sense?",
                guidance="Use compile, judge, and map preview feedback here; those tools are evidence for the layer, not closure by themselves.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_3_external_dependency_representability_completeness",
                title="Layer 3 — External dependency and representability completeness",
                question="Is anything required for honest mapping missing from the current source set, external documents, feature vocabulary, frame data, or dependency graph?",
                guidance="Record dependencies and representability gaps explicitly; do not guess missing geometry.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_4_map_handoffability_scoped_completion",
                title="Layer 4 — Map handoffability and scoped completion",
                question="Given Layers 1-3, what can be handed forward as a mapped IR/map package, what cannot, and at what scope?",
                guidance="Partial success is valid when mapped scopes, incomplete scopes, produced artifacts, and remaining needs are explicit.",
            ),
        ),
    )


def deed_to_ir_closure_semantics() -> DeedToIrClosureSemantics:
    return DeedToIrClosureSemantics(
        summary=(
            "Closure means the mappable deed scope has faithful feature-graph IR and an honest "
            "map handoff posture, while incomplete, dependency-pending, or unrepresentable scopes "
            "remain explicit instead of being hidden behind prose."
        ),
        sufficient_when=(
            "Mappable deed meaning is represented in feature-graph IR as faithfully as current information allows.",
            "IR and compiled/rendered geometry integrity have been assessed with available deterministic feedback.",
            "External dependencies, unsupported primitives, and incomplete source scopes are recorded explicitly.",
            "Final handoff states which scopes are mapped, which are incomplete or dependency-pending, and which artifact refs were produced.",
        ),
        must_remain_explicit_if_unresolved=(
            "Scopes transcript-edit marked non-forwardable.",
            "Any discovered upstream transcript issue that affects IR or map output.",
            "Missing external references, frame data, source continuations, or dependency documents.",
            "Representability gaps or unsupported primitives that prevent honest map production.",
            "Visual or geometric mismatches that remain unrepaired.",
        ),
        anti_patterns=(
            "Treating transcript-edit normalized text as a prison when downstream sanity exposes a real error.",
            "Treating compile, judge, or render as closure by itself.",
            "Collapsing blocked parcel scope into silent whole-deed readiness.",
            "Forcing geometry or fake completeness when scoped partial handoff is the honest result.",
        ),
    )
