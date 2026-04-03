from __future__ import annotations

import json

import pytest

from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.llm_turn_adapter import (
    ModelActionParseError,
    _coerce_action_plan,
)


def test_coerce_action_plan_accepts_real_json_booleans() -> None:
    plan = _coerce_action_plan(
        json.dumps(
            {
                "action_type": "select_tool",
                "action_inputs": {},
                "idempotency_key": "ik-1",
                "skip_execution": False,
                "wait_for_human": True,
                "complete_run": False,
                "rationale": "ok",
                "state_patch": None,
            }
        ),
        available_tool_ids=("select_tool",),
    )

    assert isinstance(plan, ActionPlan)
    assert plan.action_type == "select_tool"
    assert plan.skip_execution is False
    assert plan.wait_for_human is True
    assert plan.complete_run is False
    assert plan.state_patch is None


def test_coerce_action_plan_accepts_state_patch_object() -> None:
    plan = _coerce_action_plan(
        json.dumps(
            {
                "action_type": "select_tool",
                "action_inputs": {},
                "idempotency_key": "ik-2",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": None,
                "state_patch": {"resolution": {"active_item_id": "x"}},
            }
        ),
        available_tool_ids=("select_tool",),
    )
    assert plan.state_patch == {"resolution": {"active_item_id": "x"}}


def test_coerce_action_plan_rejects_non_object_state_patch() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": "nope",
    }
    with pytest.raises(ModelActionParseError, match="state_patch must be"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


@pytest.mark.parametrize("field", ["skip_execution", "wait_for_human", "complete_run"])
def test_coerce_action_plan_rejects_string_false_for_boolean_fields(field: str) -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "ok",
        "state_patch": None,
    }
    payload[field] = "false"

    with pytest.raises(ModelActionParseError, match=f"{field} must be a JSON boolean"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))
