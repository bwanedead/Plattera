"""Batch parse/execute tests for ``delegate_subtask``."""

from __future__ import annotations

import json

import pytest

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.execution.session import ExecutionSessionManager
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.action_batch import project_batch_item_row
from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response,
)
from harness.runtime.orchestration.action_sequence import ActionPlanAction
from harness.runtime.orchestration.action_sequence_hooks import _execute_sequence_items
from harness.runtime.orchestration.subtasks.batch_policy import (
    DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH,
    delegate_subtask_tool_batch_policy,
)
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.handler import make_delegate_subtask_handler
from harness.runtime.orchestration.subtasks.registry import DEFAULT_SUBTASK_REGISTRY
from harness.runtime.orchestration.tool_batch_policy import resolve_tool_batch_policies


def _delegate_inputs(*, alias: str = "local_subtask") -> dict:
    return {
        "profile": "harness.observation",
        "task": f"Inspect supplied input for {alias}.",
        "context_refs": [f"artifact:{alias}"],
    }


def _batch_payload(*, actions: list[dict]) -> str:
    return json.dumps({"actions": actions, "rationale": "Run bounded delegated observations."})


def _delegate_policies():
    return {DELEGATE_SUBTASK_ACTION_TYPE: delegate_subtask_tool_batch_policy()}


def _delegate_action(alias: str) -> dict:
    return {
        "alias": alias,
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "action_inputs": _delegate_inputs(alias=alias),
    }


class _DelegateHandlerSessionManager(ExecutionSessionManager):
    def __init__(self, *, model_caller, registry=None) -> None:
        super().__init__()
        self.handler = make_delegate_subtask_handler(
            model_caller=model_caller,
            model_name="model-a",
            hydration_handler=None,
            registry=registry or DEFAULT_SUBTASK_REGISTRY,
        )
        self.requests: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.requests.append(request)
        dispatch = self.handler(request)
        record = SessionExecutionRecord(
            session_id=request.session_id,
            run_id="r",
            request=request,
            result=dispatch,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED if dispatch.executed else ExecutionState.REFUSED,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs={}),
                budgets_remaining={},
                last_refusal=dispatch.refusal,
            ),
            refusal=dispatch.refusal,
            record=record,
        )


def test_parser_accepts_two_delegate_subtask_actions_in_one_batch() -> None:
    plan = parse_action_plan_response(
        _batch_payload(actions=[_delegate_action("read_a"), _delegate_action("read_b")]),
        available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        tool_batch_policies=_delegate_policies(),
    )
    assert len(plan.actions) == 2
    assert {row.alias for row in plan.actions} == {"read_a", "read_b"}


def test_parser_rejects_delegate_subtask_over_cap_before_execution() -> None:
    actions = [_delegate_action(f"read_{index}") for index in range(DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH + 1)]
    with pytest.raises(ModelActionParseError) as excinfo:
        parse_action_plan_response(
            _batch_payload(actions=actions),
            available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
            tool_batch_policies=_delegate_policies(),
        )
    assert excinfo.value.reason_code == "invalid_model_action_json"
    assert "cap" in str(excinfo.value).lower() or "batch" in str(excinfo.value).lower()


def test_parser_rejects_unknown_delegate_profile_before_execution() -> None:
    action = _delegate_action("bad_profile")
    action["action_inputs"]["profile"] = "harness.unknown"
    with pytest.raises(ModelActionParseError) as excinfo:
        parse_action_plan_response(
            _batch_payload(actions=[action]),
            available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
            tool_batch_policies=_delegate_policies(),
        )
    assert "unknown subtask profile" in str(excinfo.value)


def test_runner_surface_spec_resolves_delegate_batch_policy() -> None:
    from harness.runtime.orchestration.subtasks.batch_policy import delegate_subtask_tool_batch_spec

    policies = resolve_tool_batch_policies(
        {
            "harness_delegate_subtask": {
                "tool_specs": [
                    {
                        "tool_id": DELEGATE_SUBTASK_ACTION_TYPE,
                        "batching": delegate_subtask_tool_batch_spec(),
                    }
                ]
            }
        }
    )
    policy = policies[DELEGATE_SUBTASK_ACTION_TYPE]
    assert policy.allowed is True
    assert policy.max_calls_per_batch == DELEGATE_SUBTASK_MAX_CALLS_PER_BATCH
    assert policy.side_effect_class == "model_observation"
    assert policy.continues_after_item_failure is True


def test_two_delegate_subtask_actions_both_succeed() -> None:
    def model_caller(prompt: str, model_name: str, *, call_options):
        del model_name, call_options
        return json.dumps(
            {
                "status": "completed",
                "result": {
                    "reading": "A",
                    "ambiguity": "",
                    "observations": [prompt[:24]],
                    "limits": [],
                },
            }
        )

    sm = _DelegateHandlerSessionManager(model_caller=model_caller)
    actions = (
        ActionPlanAction("read_a", DELEGATE_SUBTASK_ACTION_TYPE, _delegate_inputs(alias="read_a")),
        ActionPlanAction("read_b", DELEGATE_SUBTASK_ACTION_TYPE, _delegate_inputs(alias="read_b")),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=LoopMemoryState(),
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=2,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_delegate_policies(),
        multi_action=True,
    )
    by_alias = {row["alias"]: row for row in sequence_result["items"]}
    assert by_alias["read_a"]["execution_state"] == "executed"
    assert by_alias["read_b"]["execution_state"] == "executed"
    assert by_alias["read_a"]["outputs_excerpt"]["status"] == "completed"
    assert by_alias["read_b"]["outputs_excerpt"]["status"] == "completed"
    assert sm.requests[0].inputs["_subtask_alias"] == "read_a"
    assert sm.requests[1].inputs["_subtask_alias"] == "read_b"


def test_one_malformed_child_json_does_not_fail_successful_sibling() -> None:
    calls = {"count": 0}

    def model_caller(prompt: str, model_name: str, *, call_options):
        del prompt, model_name, call_options
        calls["count"] += 1
        if calls["count"] == 2:
            return "not-json"
        return json.dumps(
            {
                "status": "completed",
                "result": {
                    "reading": "A",
                    "ambiguity": "",
                    "observations": [],
                    "limits": [],
                },
            }
        )

    sm = _DelegateHandlerSessionManager(model_caller=model_caller)
    actions = (
        ActionPlanAction("read_ok", DELEGATE_SUBTASK_ACTION_TYPE, _delegate_inputs(alias="read_ok")),
        ActionPlanAction("read_bad", DELEGATE_SUBTASK_ACTION_TYPE, _delegate_inputs(alias="read_bad")),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=LoopMemoryState(),
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=3,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_delegate_policies(),
        multi_action=True,
    )
    by_alias = {row["alias"]: row for row in sequence_result["items"]}
    assert by_alias["read_ok"]["execution_state"] == "executed"
    assert by_alias["read_ok"]["outputs_excerpt"]["status"] == "completed"
    assert by_alias["read_bad"]["execution_state"] == "executed"
    assert by_alias["read_bad"]["outputs_excerpt"]["status"] == "failed"


def test_one_validation_failure_does_not_block_successful_sibling() -> None:
    sm = _DelegateHandlerSessionManager(model_caller=lambda *args, **kwargs: "{}")
    actions = (
        ActionPlanAction("read_ok", DELEGATE_SUBTASK_ACTION_TYPE, _delegate_inputs(alias="read_ok")),
        ActionPlanAction(
            "read_bad",
            DELEGATE_SUBTASK_ACTION_TYPE,
            {"profile": "harness.observation", "task": "missing refs"},
        ),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=LoopMemoryState(),
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=4,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_delegate_policies(),
        multi_action=True,
    )
    by_alias = {row["alias"]: row for row in sequence_result["items"]}
    assert by_alias["read_ok"]["execution_state"] == "executed"
    assert by_alias["read_bad"]["execution_state"] == "retryable_error"


def test_batch_projection_contains_both_rows_without_raw_b64() -> None:
    row_ok = {
        "alias": "read_a",
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "execution_state": "executed",
        "outputs_excerpt": {
            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
            "subtask_id": "read_a",
            "profile": "harness.observation",
            "status": "completed",
            "input_refs": ["artifact:read_a"],
            "result": {"reading": "A", "ambiguity": "", "observations": [], "limits": []},
            "image_b64": "SHOULD_NOT_RENDER",
        },
    }
    row_failed = {
        "alias": "read_b",
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "execution_state": "executed",
        "outputs_excerpt": {
            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
            "subtask_id": "read_b",
            "profile": "harness.observation",
            "status": "failed",
            "input_refs": ["artifact:read_b"],
            "result": {},
            "errors": [{"reason_code": "subtask_output_malformed", "message": "bad json"}],
        },
    }
    projected = [project_batch_item_row(row) for row in (row_ok, row_failed)]
    assert projected[0]["delegate_subtask"]["status"] == "completed"
    assert projected[1]["delegate_subtask"]["status"] == "failed"
    assert projected[1]["delegate_subtask"]["errors"][0]["reason_code"] == "subtask_output_malformed"
    joined = json.dumps(projected).lower()
    assert "should_not_render" not in joined
    assert "b64" not in joined


def test_transcript_edit_visual_profile_batch_with_localized_image_refs() -> None:
    from domains.mapping.transcript_edit import build_transcript_edit_domain_pack
    from domains.mapping.transcript_edit.execution.subtask_profiles import (
        TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
    )
    from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry

    payload = build_transcript_edit_domain_pack().build_surface_payload()
    registry = build_composed_subtask_registry(
        surface_payloads={"transcript_edit": {"transcript_edit": payload}},
    )
    assert registry.get(TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID) is not None

    plan = parse_action_plan_response(
        _batch_payload(
            actions=[
                {
                    "alias": "read_bearing_a",
                    "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                    "action_inputs": {
                        "profile": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
                        "task": "Read the bearing text visible in crop A.",
                        "context_refs": ["image:derived:crop_a"],
                    },
                },
                {
                    "alias": "read_bearing_b",
                    "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
                    "action_inputs": {
                        "profile": TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
                        "task": "Read the bearing text visible in crop B.",
                        "context_refs": ["image:derived:crop_b"],
                    },
                },
            ]
        ),
        available_tool_ids=(DELEGATE_SUBTASK_ACTION_TYPE,),
        tool_batch_policies=_delegate_policies(),
        subtask_profile_registry=registry,
    )
    assert len(plan.actions) == 2


def test_transcript_edit_visual_batch_executes_with_one_truncated_sibling() -> None:
    from domains.mapping.transcript_edit.execution.subtask_profiles import (
        TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID,
        build_transcript_edit_subtask_profiles,
    )
    from harness.runtime.orchestration.subtasks.registry import build_composed_subtask_registry

    profiles = [{**build_transcript_edit_subtask_profiles()[0], "max_result_chars": 260}]
    registry = build_composed_subtask_registry(
        opaque_run_context={"subtask_profiles": profiles},
    )
    calls = {"count": 0}

    def model_caller(prompt: str, model_name: str, *, call_options):
        del prompt, model_name, call_options
        calls["count"] += 1
        if calls["count"] == 2:
            return json.dumps(
                {
                    "status": "completed",
                    "result": {
                        "task_response": "Verbose read. " + ("detail. " * 120),
                        "source_visible_text": "N. 4° 00' W.",
                        "visual_basis": ["numeral resembles 4"],
                        "ambiguity": "",
                        "limits": [],
                    },
                }
            )
        return json.dumps(
            {
                "status": "completed",
                "result": {
                    "task_response": "Crop A reads N. 2° 00' W.",
                    "source_visible_text": "N. 2° 00' W.",
                    "visual_basis": ["numeral resembles 2"],
                    "ambiguity": "",
                    "limits": [],
                },
            }
        )

    sm = _DelegateHandlerSessionManager(model_caller=model_caller, registry=registry)
    profile_id = TRANSCRIPT_EDIT_VISUAL_SOURCE_OBSERVATION_PROFILE_ID
    actions = (
        ActionPlanAction(
            "read_a",
            DELEGATE_SUBTASK_ACTION_TYPE,
            {
                "profile": profile_id,
                "task": "Read crop A bearing text.",
                "context_refs": ["image:derived:crop_a"],
            },
        ),
        ActionPlanAction(
            "read_b",
            DELEGATE_SUBTASK_ACTION_TYPE,
            {
                "profile": profile_id,
                "task": "Read crop B bearing text.",
                "context_refs": ["image:derived:crop_b"],
            },
        ),
    )
    sequence_result, _ = _execute_sequence_items(
        loop_memory=LoopMemoryState(),
        session_manager=sm,
        session_id="s",
        actions=actions,
        iteration=5,
        request_id_prefix="req",
        run_id="r",
        tool_batch_policies=_delegate_policies(),
        multi_action=True,
    )
    by_alias = {row["alias"]: row for row in sequence_result["items"]}
    assert by_alias["read_a"]["execution_state"] == "executed"
    assert by_alias["read_b"]["execution_state"] == "executed"
    assert by_alias["read_a"]["outputs_excerpt"]["status"] == "completed"
    assert by_alias["read_b"]["outputs_excerpt"]["status"] == "completed"
    assert by_alias["read_b"]["outputs_excerpt"].get("result_truncated") is True
    assert by_alias["read_b"]["delegate_subtask"]["result_truncated"] is True
    projected = [project_batch_item_row(row) for row in sequence_result["items"]]
    joined = json.dumps(projected).lower()
    assert "b64" not in joined
    assert projected[0]["delegate_subtask"]["result"]["source_visible_text"] == "N. 2° 00' W."
    assert projected[1]["delegate_subtask"]["result_truncated"] is True
