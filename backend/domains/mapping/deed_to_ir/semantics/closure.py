"""What 'done enough' means for deed-to-IR — semantic only; harness decides stopping."""

from __future__ import annotations

from dataclasses import dataclass

from domains.closure_policy import ClosureDimensionStandard, CompletionAnchorPolicy, DomainClosurePolicy


@dataclass(frozen=True)
class DeedToIrClosureSemantics:
    summary: str
    sufficient_when: tuple[str, ...]
    must_remain_explicit_if_unresolved: tuple[str, ...]
    anti_patterns: tuple[str, ...]


def build_deed_to_ir_closure_policy() -> DomainClosurePolicy:
    """Soft semantic closure policy; the harness does not author layer conclusions."""
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
        required_output_ref_for_complete="deed_to_ir:output",
        completion_anchor=CompletionAnchorPolicy(
            enabled=True,
            publish_action_ids=("finalize_current_deed_to_ir_output",),
            publish_lineage_ref_fields=("mapping_artifact_ref", "ir_artifact_ref"),
            published_preview_ref_field="final_package_preview_ref",
            require_published_preview_ref=True,
            preview_ready_publish_bypass=False,
            preview_prepare_action_ids=(),
            preview_ready_field="publish_ready_candidate",
            publish_posture_mirror_blocker_exact=(
                "ready_to_publish_false",
            ),
            publish_posture_mirror_blocker_prefixes=(
                "work_universe_not_audited:",
                "closed_items_without_earned_determination:",
                "closed_items_without_basis:",
                "closed_dimensions_without_earned_determination:",
                "closed_dimensions_without_basis:",
                "required_dimensions_missing:",
                "resolution_items_below_minimum:",
            ),
            posture_mirror_blocker_exact=(
                "ready_to_close_false",
                "skipped_resolution_rows_pending",
            ),
            posture_mirror_blocker_prefixes=(
                "work_universe_not_audited:",
                "closed_items_without_earned_determination:",
                "closed_items_without_basis:",
                "closed_dimensions_without_earned_determination:",
                "closed_dimensions_without_basis:",
                "required_dimensions_missing:",
                "resolution_items_below_minimum:",
            ),
            terminal_on_satisfied_anchor=True,
        ),
        standards=(
            ClosureDimensionStandard(
                dimension_id="layer_1_deed_meaning_to_ir_fidelity",
                title="Layer 1 — Deed meaning to IR fidelity",
                question="Has the mappable deed meaning been represented faithfully and traceably in IR, with its important values, relationships, structure, and provenance intact?",
                guidance=(
                    "Use the transcript-edit handoff as the normal substrate, but diagnose and repair "
                    "the correct layer when geometric or map sanity exposes a real upstream issue."
                ),
            ),
            ClosureDimensionStandard(
                dimension_id="layer_2_ir_geometry_integrity",
                title="Layer 2 — IR and geometry integrity",
                question="Does the resulting geometry follow the authored IR and make sense against the deed description?",
                guidance="Unexplained breaks, impossible geometry, internal contradiction, or visual mismatch keep this layer open until repaired or explicitly blocked.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_3_external_dependency_representability_completeness",
                title="Layer 3 — External dependency and representability completeness",
                question="Are missing sources, external references, frames, unsupported primitives, and other representability limits explicit?",
                guidance="Record dependencies and representability gaps explicitly; never invent geometry to hide one.",
            ),
            ClosureDimensionStandard(
                dimension_id="layer_4_map_handoffability_scoped_completion",
                title="Layer 4 — Map handoffability and scoped completion",
                question="Which scopes are honestly mapped and ready to hand forward, which remain incomplete or blocked, and which durable artifacts carry the result?",
                guidance="Partial success is valid when mapped scopes, blocked scopes, produced artifacts, and remaining needs are explicit.",
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
            "Resulting geometry follows the authored IR and makes sense against the deed description, or remaining mismatches are explicitly blocked.",
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
            "Treating schema validity, successful computation, deterministic diagnostics, or a rendered image as closure by itself.",
            "Collapsing blocked parcel scope into silent whole-deed readiness.",
            "Forcing geometry or fake completeness when scoped partial handoff is the honest result.",
        ),
    )
