"""Parser tests for action_batch."""

from __future__ import annotations

import json

import pytest

from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.tool_batch_policy import ToolBatchPolicy


def _policies() -> dict[str, ToolBatchPolicy]:
    return {
        "transform_artifact": ToolBatchPolicy(
            tool_id="transform_artifact",
            allowed=True,
            max_calls_per_batch=4,
            side_effect_class="derived_artifact",
        ),
        "hydrate_artifact_refs": ToolBatchPolicy(
            tool_id="hydrate_artifact_refs",
            allowed=True,
            max_calls_per_batch=3,
            side_effect_class="read_only",
        ),
        "noop": ToolBatchPolicy(
            tool_id="noop",
            allowed=True,
            max_calls_per_batch=2,
            side_effect_class="read_only",
        ),
    }


def test_parse_accepts_valid_batch() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_batch": [
                {"alias": "a", "action_type": "noop", "action_inputs": {}},
                {"alias": "b", "action_type": "noop", "action_inputs": {}},
            ],
            "rationale": "batch two independent reads",
        }),
        available_tool_ids=("noop",),
        tool_batch_policies=_policies(),
    )
    assert len(plan.actions) == 2
    assert plan.action_type is None


def test_parse_rejects_action_type_plus_batch() -> None:
    with pytest.raises(ModelActionParseError, match="cannot be mixed"):
        parse_action_plan_response(
            json.dumps({
                "action_type": "noop",
                "action_batch": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
                "rationale": "x",
            }),
            available_tool_ids=("noop",),
            tool_batch_policies=_policies(),
        )


def test_parse_rejects_missing_alias() -> None:
    with pytest.raises(ModelActionParseError, match="alias"):
        parse_action_plan_response(
            json.dumps({
                "action_batch": [{"action_type": "noop", "action_inputs": {}}],
                "rationale": "x",
            }),
            available_tool_ids=("noop",),
            tool_batch_policies=_policies(),
        )


def test_parse_rejects_duplicate_alias() -> None:
    with pytest.raises(ModelActionParseError, match="duplicate"):
        parse_action_plan_response(
            json.dumps({
                "action_batch": [
                    {"alias": "a", "action_type": "noop", "action_inputs": {}},
                    {"alias": "a", "action_type": "noop", "action_inputs": {}},
                ],
                "rationale": "x",
            }),
            available_tool_ids=("noop",),
            tool_batch_policies=_policies(),
        )


def test_parse_rejects_invalid_alias() -> None:
    with pytest.raises(ModelActionParseError, match="alias"):
        parse_action_plan_response(
            json.dumps({
                "action_batch": [
                    {"alias": "bad.alias", "action_type": "noop", "action_inputs": {}},
                ],
                "rationale": "x",
            }),
            available_tool_ids=("noop",),
            tool_batch_policies=_policies(),
        )


def test_parse_rejects_too_large_batch() -> None:
    items = [
        {"alias": f"i{i}", "action_type": "noop", "action_inputs": {}}
        for i in range(6)
    ]
    with pytest.raises(ModelActionParseError, match="max batch size"):
        parse_action_plan_response(
            json.dumps({"action_batch": items, "rationale": "x"}),
            available_tool_ids=("noop",),
            tool_batch_policies=_policies(),
        )


def test_parse_rejects_non_batchable_tool() -> None:
    with pytest.raises(ModelActionParseError, match="not batchable"):
        parse_action_plan_response(
            json.dumps({
                "action_batch": [
                    {"alias": "s", "action_type": "save_workspace_artifact", "action_inputs": {}},
                ],
                "rationale": "x",
            }),
            available_tool_ids=("save_workspace_artifact",),
            tool_batch_policies=_policies(),
        )


def test_parse_accepts_hydrate_next_with_batch_placeholders() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_batch": [
                {"alias": "c1", "action_type": "transform_artifact", "action_inputs": {"ref_id": "r"}},
            ],
            "hydrate_next": ["@batch.c1.result.derived_ref_id"],
            "rationale": "x",
        }),
        available_tool_ids=("transform_artifact",),
        tool_batch_policies=_policies(),
    )
    assert plan.hydrate_next == ("@batch.c1.result.derived_ref_id",)
