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
    """Brief A: soft policy skeleton; hard enforcement arrives with save/compile/judge tools."""
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
            "ir_representability",
            "compile_readiness",
            "judge_gaps",
        ),
        required_output_ref_for_complete=None,
        standards=(
            ClosureDimensionStandard(
                dimension_id="ir_representability",
                title="IR representability",
                question="Can the scoped deed meaning be encoded in feature-graph IR without silent gaps?",
                guidance="Record explicit gaps when meaning cannot be represented yet.",
            ),
            ClosureDimensionStandard(
                dimension_id="compile_readiness",
                title="Compile readiness",
                question="Which scoped IR artifacts are ready for compile attempts vs blocked?",
                guidance="Compile gaps are honest downstream facts, not failures to hide.",
            ),
            ClosureDimensionStandard(
                dimension_id="judge_gaps",
                title="Judge gaps",
                question="Which scoped IR claims remain unjudged or blocked?",
                guidance="Do not treat compile/judge absence as earned closure.",
            ),
        ),
    )


def deed_to_ir_closure_semantics() -> DeedToIrClosureSemantics:
    return DeedToIrClosureSemantics(
        summary=(
            "Closure means scoped deed meaning is represented in IR where possible, "
            "with compile/judge gaps and blocked scopes explicit — not hidden behind prose."
        ),
        sufficient_when=(
            "Forwardable transcript-edit scopes have corresponding IR work tracked or explicitly deferred.",
            "Blocked or partial scopes remain labeled with inherited transcript-edit metadata.",
            "Compile/judge gaps are recorded as downstream facts when tools exist.",
        ),
        must_remain_explicit_if_unresolved=(
            "Scopes transcript-edit marked non-forwardable.",
            "Missing IR tooling or unimplemented save/compile/judge paths.",
            "Representability gaps that prevent geometry compilation.",
        ),
        anti_patterns=(
            "Treating transcript-edit normalized text as earned IR.",
            "Implying compile success before compile tools run.",
            "Collapsing blocked parcel scope into silent whole-deed readiness.",
        ),
    )
