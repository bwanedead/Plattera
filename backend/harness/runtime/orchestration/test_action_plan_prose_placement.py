from __future__ import annotations

import json
from typing import Any

import pytest

from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.action_plan_prose_placement import (
    normalize_misplaced_action_plan_prose,
)
from harness.runtime.orchestration.llm_turn_choose_action_support import build_repair_audit_record
from harness.runtime.orchestration.repair_lane import (
    REPAIR_METHOD_DETERMINISTIC_STRUCTURE,
    REPAIR_METHOD_MODEL,
    attempt_repair,
)


_RESOLUTION_PATCH = {
    "mission": {"active_mode": "investigating"},
    "resolution": {
        "active_item_id": "item-1",
        "items": [
            {
                "item_id": "item-1",
                "title": "Unverified claim",
                "kind": "open_question",
                "status": "open",
            }
        ],
    },
}

_RATIONALE = "Keep the authored resolution rows and record why this move earns the next close."
_OPERATOR_PROGRESS = "Updating the resolution graph from the already-authored patch."


def _state_only_with_nested_prose() -> dict[str, Any]:
    return {
        "action_type": None,
        "action_inputs": {},
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": {
            **_RESOLUTION_PATCH,
            "rationale": _RATIONALE,
            "operator_progress_message": _OPERATOR_PROGRESS,
        },
        "continuity_journal_entry": {"note": "kept at root"},
    }


def _original_exc() -> ModelActionParseError:
    return ModelActionParseError(
        "invalid_model_action_json",
        "rationale is required on every turn: short decision note with why-this-move and expected-gain",
    )


def _explode_if_called(prompt: str, model: str, **_kwargs: Any) -> str:
    del prompt, model
    raise AssertionError("model caller must not be invoked")


def test_parser_rejects_nested_prose_without_root_rationale() -> None:
    with pytest.raises(ModelActionParseError, match="rationale is required"):
        parse_action_plan_response(
            json.dumps(_state_only_with_nested_prose()),
            available_tool_ids=("noop",),
        )


def test_deterministic_repair_salvages_nested_rationale_and_operator_progress() -> None:
    payload = _state_only_with_nested_prose()
    attempt = attempt_repair(
        model_caller=_explode_if_called,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=json.dumps(payload),
        original_exc=_original_exc(),
        available_tool_ids=("noop",),
    )
    assert attempt.repair_parse_ok is True
    assert attempt.repair_method == REPAIR_METHOD_DETERMINISTIC_STRUCTURE
    assert attempt.repair_transformations == (
        "move_state_patch_rationale_to_root",
        "move_state_patch_operator_progress_message_to_root",
    )
    plan = attempt.repair_parsed_action_plan
    assert plan is not None
    assert plan.rationale == _RATIONALE
    assert plan.operator_progress_message == _OPERATOR_PROGRESS
    assert plan.state_patch == _RESOLUTION_PATCH
    assert attempt.repair_raw_response_text == json.dumps(payload)


def test_model_repair_response_nested_rationale_is_normalized_before_parse() -> None:
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        return json.dumps(_state_only_with_nested_prose())

    attempt = attempt_repair(
        model_caller=caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text="not-json",
        original_exc=_original_exc(),
        available_tool_ids=("noop",),
    )
    assert len(calls) == 1
    assert attempt.repair_parse_ok is True
    assert attempt.repair_method == REPAIR_METHOD_MODEL
    assert "move_state_patch_rationale_to_root" in attempt.repair_transformations
    assert attempt.repair_parsed_action_plan is not None
    assert attempt.repair_parsed_action_plan.rationale == _RATIONALE
    assert attempt.repair_raw_response_text == json.dumps(_state_only_with_nested_prose())


def test_equal_root_and_nested_values_remove_only_nested_copy() -> None:
    payload = {
        "rationale": _RATIONALE,
        "operator_progress_message": _OPERATOR_PROGRESS,
        "state_patch": {
            **_RESOLUTION_PATCH,
            "rationale": _RATIONALE,
            "operator_progress_message": _OPERATOR_PROGRESS,
        },
    }
    result = normalize_misplaced_action_plan_prose(payload)
    assert result.payload["rationale"] == _RATIONALE
    assert result.payload["operator_progress_message"] == _OPERATOR_PROGRESS
    assert result.payload["state_patch"] == _RESOLUTION_PATCH
    assert result.transformations == (
        "remove_equal_nested_rationale",
        "remove_equal_nested_operator_progress_message",
    )


def test_conflicting_root_and_nested_values_are_not_chosen() -> None:
    payload = {
        "rationale": "root rationale",
        "state_patch": {**_RESOLUTION_PATCH, "rationale": "nested rationale"},
    }
    result = normalize_misplaced_action_plan_prose(payload)
    assert result.transformations == ()
    assert result.payload["rationale"] == "root rationale"
    assert result.payload["state_patch"]["rationale"] == "nested rationale"
    assert result.payload["state_patch"]["resolution"] == _RESOLUTION_PATCH["resolution"]


def test_nested_continuity_journal_entry_moves_to_root() -> None:
    payload = {
        "rationale": _RATIONALE,
        "state_patch": {
            **_RESOLUTION_PATCH,
            "continuity_journal_entry": {"step": "already authored"},
        },
    }
    result = normalize_misplaced_action_plan_prose(payload)
    assert result.payload["continuity_journal_entry"] == {"step": "already authored"}
    assert "continuity_journal_entry" not in result.payload["state_patch"]
    assert result.payload["state_patch"] == _RESOLUTION_PATCH
    assert result.transformations == ("move_state_patch_continuity_journal_entry_to_root",)


def test_invalid_nested_field_types_are_not_lifted() -> None:
    payload = {
        "state_patch": {
            **_RESOLUTION_PATCH,
            "rationale": 12,
            "operator_progress_message": ["not a string"],
            "continuity_journal_entry": "not an object",
        }
    }
    result = normalize_misplaced_action_plan_prose(payload)
    assert result.transformations == ()
    assert result.payload["state_patch"]["rationale"] == 12
    assert "rationale" not in result.payload


def test_semantic_and_control_fields_are_never_relocated() -> None:
    payload = {
        "state_patch": {
            **_RESOLUTION_PATCH,
            "rationale": _RATIONALE,
            "complete_run": True,
            "wait_for_human": True,
            "actions": [{"alias": "a", "action_type": "noop"}],
            "action_type": "noop",
            "action_inputs": {"x": 1},
            "hitl_request": {"message": "stop"},
            "pin_refs": ["artifact://a"],
            "hydrate_next": ["artifact://b"],
        }
    }
    result = normalize_misplaced_action_plan_prose(payload)
    assert result.transformations == ("move_state_patch_rationale_to_root",)
    patch = result.payload["state_patch"]
    assert result.payload["rationale"] == _RATIONALE
    assert "rationale" not in patch
    assert patch["complete_run"] is True
    assert patch["wait_for_human"] is True
    assert patch["actions"] == [{"alias": "a", "action_type": "noop"}]
    assert patch["action_type"] == "noop"
    assert patch["action_inputs"] == {"x": 1}
    assert patch["hitl_request"] == {"message": "stop"}
    assert patch["pin_refs"] == ["artifact://a"]
    assert patch["hydrate_next"] == ["artifact://b"]
    assert patch["resolution"] == _RESOLUTION_PATCH["resolution"]


def test_unrelated_repair_still_uses_model_path() -> None:
    calls: list[str] = []
    repaired = {
        "action_type": "noop",
        "action_inputs": {},
        "skip_execution": True,
        "rationale": "repaired by model",
        "state_patch": None,
        "continuity_journal_entry": {"repair": True},
    }

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        return json.dumps(repaired)

    attempt = attempt_repair(
        model_caller=caller,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text="not-json",
        original_exc=_original_exc(),
        available_tool_ids=("noop",),
    )
    assert len(calls) == 1
    assert attempt.repair_method == REPAIR_METHOD_MODEL
    assert attempt.repair_transformations == ()
    assert attempt.repair_parse_ok is True
    assert attempt.repair_parsed_action_plan is not None
    assert attempt.repair_parsed_action_plan.rationale == "repaired by model"


def test_repair_audit_record_exposes_method_and_transformations() -> None:
    attempt = attempt_repair(
        model_caller=_explode_if_called,
        model_name="fake",
        prior_prompt_mode="full_choose_action",
        previous_response_text=json.dumps(_state_only_with_nested_prose()),
        original_exc=_original_exc(),
        available_tool_ids=("noop",),
    )
    record = build_repair_audit_record(attempt)
    assert record["repair_method"] == REPAIR_METHOD_DETERMINISTIC_STRUCTURE
    assert record["repair_transformations"] == [
        "move_state_patch_rationale_to_root",
        "move_state_patch_operator_progress_message_to_root",
    ]
    assert record["repair_raw_response_text"] == json.dumps(_state_only_with_nested_prose())
    assert record["repair_parse_ok"] is True
