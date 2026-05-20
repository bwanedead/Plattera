"""Parser tests for native ``actions`` and legacy lowering."""

from __future__ import annotations

import json

import pytest

from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.action_sequence import DEFAULT_SINGLE_ACTION_ALIAS
from harness.runtime.orchestration.tool_batch_policy import ToolBatchPolicy


def _policies() -> dict[str, ToolBatchPolicy]:
    return {
        "transform_artifact": ToolBatchPolicy(
            tool_id="transform_artifact",
            allowed=True,
            max_calls_per_batch=4,
            side_effect_class="derived_artifact",
        ),
        "noop": ToolBatchPolicy(
            tool_id="noop",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class="read_only",
        ),
    }


def test_parse_accepts_native_single_action() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "actions": [
                {
                    "alias": "crop_a",
                    "action_type": "transform_artifact",
                    "action_inputs": {"ref_id": "r1"},
                    "hydrate_next": ["@this.result.derived_ref_id"],
                    "hydrate_next_reason": "inspect crop",
                },
            ],
            "rationale": "one native action",
        }),
        available_tool_ids=("transform_artifact",),
        tool_batch_policies=_policies(),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].alias == "crop_a"
    assert plan.actions[0].hydrate_next == ("@this.result.derived_ref_id",)


def test_parse_accepts_native_multi_action() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "actions": [
                {"alias": "a", "action_type": "noop", "action_inputs": {}},
                {"alias": "b", "action_type": "noop", "action_inputs": {}},
            ],
            "rationale": "two native actions",
        }),
        available_tool_ids=("noop",),
        tool_batch_policies=_policies(),
    )
    assert len(plan.actions) == 2


def test_parse_rejects_mixed_native_and_legacy() -> None:
    with pytest.raises(ModelActionParseError, match="cannot be mixed"):
        parse_action_plan_response(
            json.dumps({
                "actions": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
                "action_type": "noop",
                "rationale": "x",
            }),
            available_tool_ids=("noop",),
            tool_batch_policies=_policies(),
        )


def test_parse_lowers_legacy_action_type_to_actions() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_type": "noop",
            "action_inputs": {"k": 1},
            "hydrate_next": ["@result.derived_ref_id"],
            "rationale": "legacy single",
        }),
        available_tool_ids=("noop",),
        tool_batch_policies=_policies(),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].alias == DEFAULT_SINGLE_ACTION_ALIAS
    assert plan.actions[0].hydrate_next == ("@result.derived_ref_id",)


def test_parse_native_single_action_does_not_require_batch_policy() -> None:
    """Native ``actions`` length 1 must not be gated by tool batching metadata."""
    plan = parse_action_plan_response(
        json.dumps({
            "actions": [
                {
                    "alias": "save_row",
                    "action_type": "save_workspace_artifact",
                    "action_inputs": {},
                },
            ],
            "rationale": "single native save",
        }),
        available_tool_ids=("save_workspace_artifact",),
        tool_batch_policies={},
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].alias == "save_row"


def test_parse_lowers_legacy_action_batch_to_actions() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_batch": [
                {"alias": "a", "action_type": "noop", "action_inputs": {}},
            ],
            "rationale": "legacy batch",
        }),
        available_tool_ids=("noop",),
        tool_batch_policies=_policies(),
    )
    assert len(plan.actions) == 1
    assert plan.actions[0].alias == "a"
