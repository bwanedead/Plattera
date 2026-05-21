"""Unit tests for required output-tier complete_run gate."""

from __future__ import annotations

from harness.mission_state import (
    ClosureDimension,
    ClosureState,
    new_mission_state,
    new_resolution_state,
    ResolutionItem,
)
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import ActionPlan, ActionPlanAction
from harness.runtime.orchestration.orchestrator_policy import closure_enforcement_failure
from harness.runtime.orchestration.required_output_gate import (
    MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS,
    latest_refs_contains_required_output,
    maybe_reset_missing_required_output_counter,
    required_output_artifact_enforcement_failure,
)


def _ready_memory(*, latest_refs: dict[str, str] | None = None) -> LoopMemoryState:
    mem = LoopMemoryState()
    ms = new_mission_state(mission_id="m-out", loop_family="orchestration_kernel")
    ms = ms.model_copy(
        update={
            "work_universe_posture": "audited",
            "closure_state": ClosureState(
                dimensions=[
                    ClosureDimension(dimension_id="layer_a", title="a", status="closed"),
                ],
                ready_to_close=True,
                ready_to_publish=True,
            ),
        }
    )
    rs = new_resolution_state().model_copy(
        update={
            "items": [
                ResolutionItem(
                    item_id="i1",
                    title="i1",
                    kind="work_unit",
                    status="closed",
                )
            ]
        }
    )
    ms = ms.model_copy(update={"resolution_state": rs})
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    if latest_refs is not None:
        mem.continuity.latest_refs = dict(latest_refs)
    return mem


def _policy_with_required_output() -> dict[str, object]:
    return {
        "hard_enforced": True,
        "enforce_on_complete": True,
        "required_output_ref_for_complete": "transcript_edit:output",
        "required_dimension_ids": ["layer_a"],
        "minimum_resolution_items_for_complete": 1,
        "publish_action_ids": ["publish_workspace_artifact"],
    }


def test_complete_run_blocked_without_output_ref() -> None:
    mem = _ready_memory(latest_refs={"working": "transcript_edit:working:rev:0002"})
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _policy_with_required_output()}
    failure = closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan)
    assert failure is not None
    assert failure[0] == "missing_required_output_artifact:transcript_edit:output"


def test_complete_run_allowed_with_output_ref_key() -> None:
    mem = _ready_memory(latest_refs={"transcript_edit:output": "artifact://out"})
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _policy_with_required_output()}
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_complete_run_allowed_with_output_ref_value() -> None:
    mem = _ready_memory(latest_refs={"published": "transcript_edit:output"})
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": _policy_with_required_output()}
    assert closure_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_domains_without_required_output_unaffected() -> None:
    mem = _ready_memory()
    plan = ActionPlan(complete_run=True)
    ctx = {"domain_closure_policy": {"hard_enforced": True, "enforce_on_complete": True}}
    assert required_output_artifact_enforcement_failure(run_ctx=ctx, loop_memory=mem, action_plan=plan) is None


def test_counter_resets_when_output_ref_appears() -> None:
    mem = _ready_memory()
    mem.continuity.missing_required_output_complete_attempts = 2
    mem.continuity.latest_refs = {"transcript_edit:output": "artifact://x"}
    maybe_reset_missing_required_output_counter(
        run_ctx={"domain_closure_policy": _policy_with_required_output()},
        loop_memory=mem,
    )
    assert mem.continuity.missing_required_output_complete_attempts == 0


def test_counter_resets_on_publish_action() -> None:
    mem = _ready_memory()
    mem.continuity.missing_required_output_complete_attempts = 2
    plan = ActionPlan(
        actions=(
            ActionPlanAction(
                alias="a",
                action_type="publish_workspace_artifact",
                action_inputs={},
            ),
        )
    )
    maybe_reset_missing_required_output_counter(
        run_ctx={"domain_closure_policy": _policy_with_required_output()},
        loop_memory=mem,
        action_plan=plan,
    )
    assert mem.continuity.missing_required_output_complete_attempts == 0


def test_latest_refs_contains_required_output() -> None:
    assert latest_refs_contains_required_output({"k": "transcript_edit:output"}, "transcript_edit:output")
    assert not latest_refs_contains_required_output({"k": "transcript_edit:working"}, "transcript_edit:output")


def test_max_consecutive_attempts_constant() -> None:
    assert MAX_CONSECUTIVE_MISSING_OUTPUT_COMPLETE_ATTEMPTS == 3
