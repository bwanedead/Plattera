from __future__ import annotations

import json
import pytest

from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)


def test_parse_action_plan_unwraps_author_payload_continuity_wrapper() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "ik-wrap-1",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": "dispatch",
                "state_patch": None,
                "continuity_journal_entry": {
                    "kernel_turn_index": 14,
                    "author_payload": {"step": "integrated hitl answer", "open_threads": ["continue audit sweep"]},
                },
                "operator_progress_message": None,
                "hitl_request": None,
                "hitl_consumed_prompt_ids": None,
            }
        ),
        available_tool_ids=("noop",),
    )
    assert plan.continuity_journal_entry == {
        "step": "integrated hitl answer",
        "open_threads": ["continue audit sweep"],
    }


def test_parse_action_plan_accepts_minimal_dispatch_without_booleans() -> None:
    plan = parse_action_plan_response(
        json.dumps({"action_type": "noop", "action_inputs": {"x": 1}, "rationale": "dispatch"}),
        available_tool_ids=("noop",),
    )

    assert plan.action_type == "noop"
    assert plan.action_inputs == {"x": 1}
    assert plan.skip_execution is False
    assert plan.wait_for_human is False
    assert plan.complete_run is False
    assert plan.idempotency_key == ""
    assert plan.rationale == "dispatch"


def test_parse_action_plan_accepts_minimal_state_only_patch_without_booleans() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "state_patch": {"resolution": {"active_item_id": "item-1"}},
                "rationale": "focus on item-1",
            }
        ),
        available_tool_ids=("noop",),
    )

    assert plan.action_type is None
    assert plan.skip_execution is True
    assert plan.wait_for_human is False
    assert plan.complete_run is False
    assert plan.state_patch == {"resolution": {"active_item_id": "item-1"}}


def test_parse_action_plan_accepts_async_hitl_without_wait_boolean() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "hitl_request": {"message": "Need a ruling", "choices": [], "context": {}},
                "state_patch": {"resolution": {"items": [{"item_id": "item-1", "requires_hitl": True}]}},
                "rationale": "async HITL",
            }
        ),
        available_tool_ids=("noop",),
    )

    assert plan.action_type is None
    assert plan.skip_execution is True
    assert plan.wait_for_human is False
    assert plan.hitl_request is not None


def test_parse_action_plan_accepts_blocking_hitl_with_explicit_wait_for_human() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "wait_for_human": True,
                "hitl_request": {"message": "Need operator input", "choices": [], "context": {}},
                "state_patch": {"mission": {"waiting_summary": "Awaiting answer"}},
                "rationale": "blocking HITL",
            }
        ),
        available_tool_ids=("noop",),
    )

    assert plan.wait_for_human is True
    assert plan.hitl_request is not None


def test_parse_action_plan_treats_hitl_without_wait_for_human_as_async() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "hitl_request": {"message": "Need operator input", "choices": [], "context": {}},
                "state_patch": {"mission": {"waiting_summary": "Awaiting answer"}},
                "rationale": "async HITL fallback",
            }
        ),
        available_tool_ids=("noop",),
    )

    assert plan.wait_for_human is False


def test_parse_action_plan_accepts_complete_turn_with_only_complete_run_and_state_patch() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "complete_run": True,
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "rationale": "audit done",
            }
        ),
        available_tool_ids=("noop",),
    )

    assert plan.complete_run is True
    assert plan.action_type is None
    assert plan.skip_execution is False


def test_parse_action_plan_accepts_missing_idempotency_key() -> None:
    plan = parse_action_plan_response(
        json.dumps({"action_type": "noop", "rationale": "minimal"}),
        available_tool_ids=("noop",),
    )
    assert plan.idempotency_key == ""


def test_parse_action_plan_rejects_missing_rationale() -> None:
    with pytest.raises(ModelActionParseError, match="rationale is required"):
        parse_action_plan_response(
            json.dumps({"action_type": "noop", "action_inputs": {}}),
            available_tool_ids=("noop",),
        )


def test_parse_action_plan_rejects_blank_rationale() -> None:
    with pytest.raises(ModelActionParseError, match="rationale must be a non-empty string"):
        parse_action_plan_response(
            json.dumps({"action_type": "noop", "rationale": "   "}),
            available_tool_ids=("noop",),
        )


def test_parse_action_plan_rejects_non_string_rationale() -> None:
    with pytest.raises(ModelActionParseError, match="rationale must be a string"):
        parse_action_plan_response(
            json.dumps({"action_type": "noop", "rationale": 42}),
            available_tool_ids=("noop",),
        )


def test_parse_action_plan_missing_rationale_is_repairable() -> None:
    from harness.runtime.orchestration.action_plan_parser import is_repairable_action_plan_error

    try:
        parse_action_plan_response(
            json.dumps({"action_type": "noop"}),
            available_tool_ids=("noop",),
        )
    except ModelActionParseError as exc:
        assert is_repairable_action_plan_error(exc.reason_code)
    else:
        raise AssertionError("expected ModelActionParseError for missing rationale")


def test_parse_action_plan_preserves_legacy_full_payload() -> None:
    plan = parse_action_plan_response(
        json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "ik-legacy",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": "legacy payload",
                "state_patch": None,
                "continuity_journal_entry": {"step": "legacy"},
                "operator_progress_message": None,
                "hitl_request": None,
                "hitl_consumed_prompt_ids": None,
            }
        ),
        available_tool_ids=("noop",),
    )

    assert plan.action_type == "noop"
    assert plan.idempotency_key == "ik-legacy"
    assert plan.skip_execution is False


@pytest.mark.parametrize("field", ["skip_execution", "wait_for_human", "complete_run"])
def test_parse_action_plan_rejects_non_boolean_when_present(field: str) -> None:
    payload = {"action_type": "noop", field: "false"}
    with pytest.raises(ModelActionParseError, match=f"{field} must be a JSON boolean"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))
