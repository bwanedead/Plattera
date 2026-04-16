from __future__ import annotations

import json

from harness.runtime.orchestration.action_plan_parser import parse_action_plan_response


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
