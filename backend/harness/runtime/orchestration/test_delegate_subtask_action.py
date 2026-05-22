from __future__ import annotations

import json

import pytest

from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry


def _payload(action_inputs: dict) -> str:
    return json.dumps(
        {
            "actions": [
                {
                    "alias": "local_subtask",
                    "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                    "action_inputs": action_inputs,
                }
            ],
            "rationale": "Run a bounded isolated observation.",
        }
    )


def test_parser_accepts_valid_delegate_subtask_action() -> None:
    plan = parse_action_plan_response(
        _payload(
            {
                "profile": "harness.observation",
                "task": "Inspect the supplied input and answer the local question.",
                "context_refs": ["artifact:sample"],
                "isolation": {"omit_parent_graph": True, "omit_peer_candidates": True},
                "output_contract": {"kind": "observation"},
            }
        ),
        available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
    )

    assert len(plan.actions) == 1
    assert plan.actions[0].action_type == DELEGATE_SUBTASK_ACTION_TYPE
    assert plan.actions[0].alias == "local_subtask"


def test_parser_rejects_missing_delegate_subtask_fields_repairably() -> None:
    with pytest.raises(ModelActionParseError) as excinfo:
        parse_action_plan_response(
            _payload({"profile": "harness.observation", "task": "missing refs"}),
            available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        )

    assert excinfo.value.reason_code == "invalid_model_action_json"
    assert "context_refs" in str(excinfo.value)


def test_parser_rejects_unknown_delegate_profile_repairably() -> None:
    with pytest.raises(ModelActionParseError) as excinfo:
        parse_action_plan_response(
            _payload(
                {
                    "profile": "harness.unknown",
                    "task": "Inspect the supplied input.",
                    "context_refs": ["artifact:sample"],
                }
            ),
            available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        )

    assert excinfo.value.reason_code == "invalid_model_action_json"
    assert "unknown subtask profile" in str(excinfo.value)


def test_parser_rejects_delegate_ref_kind_disallowed_repairably() -> None:
    registry = build_composed_subtask_registry(
        surface_payloads={
            "test": {
                "subtask_profiles": [
                    {
                        "profile_id": "test.text_observation",
                        "owner": "test",
                        "description": "text only",
                        "allowed_ref_kinds": ["artifact", "text"],
                        "prompt_preamble": "observe",
                    }
                ]
            }
        }
    )
    with pytest.raises(ModelActionParseError) as excinfo:
        parse_action_plan_response(
            _payload(
                {
                    "profile": "test.text_observation",
                    "task": "Inspect the supplied input.",
                    "context_refs": ["image:derived:sample"],
                }
            ),
            available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
            subtask_profile_registry=registry,
        )

    assert excinfo.value.reason_code == "invalid_model_action_json"
    assert "does not allow ref kind image" in str(excinfo.value)


def test_parser_accepts_composed_domain_profile() -> None:
    registry = build_composed_subtask_registry(
        surface_payloads={
            "domain": {
                "subtask_profiles": [
                    {
                        "profile_id": "domain.visual_observation",
                        "owner": "domain",
                        "description": "opaque domain profile",
                        "allowed_ref_kinds": ["image"],
                        "prompt_preamble": "observe image",
                    }
                ]
            }
        }
    )

    plan = parse_action_plan_response(
        _payload(
            {
                "profile": "domain.visual_observation",
                "task": "Inspect supplied image.",
                "context_refs": ["image:derived:sample"],
            }
        ),
        available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        subtask_profile_registry=registry,
    )

    assert plan.actions[0].action_inputs["profile"] == "domain.visual_observation"
