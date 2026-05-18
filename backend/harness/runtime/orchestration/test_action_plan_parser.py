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


# ---------------------------------------------------------------------------
# user_message_consumed_ids + user_message_defers fields
# ---------------------------------------------------------------------------

def test_parse_action_plan_accepts_user_message_consumed_ids() -> None:
    payload = {
        "action_type": "noop",
        "rationale": "ack user message",
        "user_message_consumed_ids": ["user-msg-1", "user-msg-2"],
    }
    plan = parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))
    assert plan.user_message_consumed_ids == ("user-msg-1", "user-msg-2")


def test_parse_action_plan_accepts_user_message_defers() -> None:
    payload = {
        "action_type": "noop",
        "rationale": "defer for hitl",
        "user_message_defers": [
            {"message_id": "user-msg-1", "reason": "waiting for hitl answer"},
        ],
    }
    plan = parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))
    assert plan.user_message_defers == (
        {"message_id": "user-msg-1", "reason": "waiting for hitl answer"},
    )


def test_parse_action_plan_user_message_ack_only_no_dispatch_turn_is_valid() -> None:
    """A turn that only consumes user messages (no state_patch, no HITL) is allowed."""
    payload = {
        "action_type": None,
        "skip_execution": True,
        "rationale": "ack and move on",
        "user_message_consumed_ids": ["user-msg-1"],
    }
    plan = parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))
    assert plan.skip_execution is True
    assert plan.user_message_consumed_ids == ("user-msg-1",)


def test_parse_action_plan_user_message_defer_only_no_dispatch_turn_is_valid() -> None:
    payload = {
        "action_type": None,
        "rationale": "explicit defer",
        "user_message_defers": [{"message_id": "user-msg-1", "reason": "not in scope"}],
    }
    plan = parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))
    assert plan.skip_execution is True


def test_parse_action_plan_user_message_consumed_ids_must_be_list_of_strings() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "user_message_consumed_ids": [42, "ok"],
    }
    with pytest.raises(ModelActionParseError, match="user_message_consumed_ids"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))


def test_parse_action_plan_user_message_defers_must_have_reason() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "user_message_defers": [{"message_id": "user-msg-1"}],  # missing reason
    }
    with pytest.raises(ModelActionParseError, match="user_message_defers"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))


def test_parse_action_plan_user_message_defers_reject_blank_message_id() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "user_message_defers": [{"message_id": "  ", "reason": "x"}],
    }
    with pytest.raises(ModelActionParseError, match="user_message_defers"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))


# ---------------------------------------------------------------------------
# hydrate_next + hydrate_next_reason fields
# ---------------------------------------------------------------------------

def test_parse_action_plan_absent_hydrate_next_is_empty_tuple() -> None:
    plan = parse_action_plan_response(
        json.dumps({"action_type": "noop", "rationale": "t"}),
        available_tool_ids=("noop",),
    )
    assert plan.hydrate_next == ()
    assert plan.hydrate_next_reason is None


def test_parse_action_plan_accepts_literal_hydrate_next() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_type": "noop", "rationale": "t",
            "hydrate_next": ["artifact://x", "artifact://y"],
        }),
        available_tool_ids=("noop",),
    )
    assert plan.hydrate_next == ("artifact://x", "artifact://y")


def test_parse_action_plan_accepts_hydrate_next_placeholders() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_type": "save_workspace_artifact", "rationale": "t",
            "hydrate_next": ["@result.revision_ref", "@result.artifact_refs[]"],
        }),
        available_tool_ids=("save_workspace_artifact",),
    )
    assert plan.hydrate_next == ("@result.revision_ref", "@result.artifact_refs[]")


def test_parse_action_plan_accepts_hydrate_next_reason() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_type": "noop", "rationale": "t",
            "hydrate_next": ["@result.revision_ref"],
            "hydrate_next_reason": "inspect saved payload",
        }),
        available_tool_ids=("noop",),
    )
    assert plan.hydrate_next_reason == "inspect saved payload"


def test_parse_action_plan_clamps_overlong_hydrate_next_reason() -> None:
    plan = parse_action_plan_response(
        json.dumps({
            "action_type": "noop", "rationale": "t",
            "hydrate_next_reason": "x" * 800,
        }),
        available_tool_ids=("noop",),
    )
    assert plan.hydrate_next_reason is not None
    assert len(plan.hydrate_next_reason) == 400


def test_parse_action_plan_rejects_hydrate_next_over_max_length() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "hydrate_next": [f"r-{i}" for i in range(6)],
    }
    with pytest.raises(ModelActionParseError, match="hydrate_next"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))


def test_parse_action_plan_rejects_non_string_hydrate_next_entries() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "hydrate_next": ["ok", 42],
    }
    with pytest.raises(ModelActionParseError, match="hydrate_next entries"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))


def test_parse_action_plan_rejects_non_list_hydrate_next() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "hydrate_next": "artifact://x",
    }
    with pytest.raises(ModelActionParseError, match="hydrate_next"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))


def test_parse_action_plan_rejects_non_string_hydrate_next_reason() -> None:
    payload = {
        "action_type": "noop", "rationale": "t",
        "hydrate_next_reason": 42,
    }
    with pytest.raises(ModelActionParseError, match="hydrate_next_reason"):
        parse_action_plan_response(json.dumps(payload), available_tool_ids=("noop",))
