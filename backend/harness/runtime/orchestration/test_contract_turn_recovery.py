"""MAPDEP-BR-019: bounded turn recovery after contract-repair failure."""

from __future__ import annotations

import json
from typing import Any

import pytest

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.orchestration.action_plan_parser import ModelActionParseError
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.lifecycle import OrchestrationLifecycle
from harness.runtime.orchestration.llm_prompt_builder import (
    build_choose_action_prompt_document,
    build_turn_recovery_prompt_document,
)
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.repair_lane import REPAIR_METHOD_MODEL, RepairAttempt
from harness.runtime.orchestration.recoverable_turn_failure import (
    CORE_FAILURE_RECORD_KEYS,
    FAILURE_RECORD_COMPACT_JSON_CAP,
    PARSE_ERROR_PREVIEW_CHARS,
    POST_REPAIR_PARSE_FAILURE_STAGE,
    QUEUED_TURN_RECOVERY_DISPOSITION,
    RecoverableTurnFailure,
    build_post_repair_contract_failure_record,
    compact_failure_record_size,
    is_recoverable_output_failure,
    is_recoverable_post_repair_contract_failure,
)
from harness.runtime.orchestration.resumable_model_interruption import ResumableModelInterruption
from harness.runtime.orchestration.turn_recovery_instruction import TURN_RECOVERY_INSTRUCTION


_CONTRACT_INVALID_JSON = json.dumps(
    {
        "actions": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
        "complete_run": False,
    }
)

_VALID_DISPATCH_JSON = json.dumps(
    {
        "actions": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
        "rationale": "recover with the smallest canonical next action",
    }
)

_VALID_COMPLETE_JSON = json.dumps(
    {
        "complete_run": True,
        "rationale": "recovered with a bounded action",
        "state_patch": {"mission": {"work_universe_posture": "audited"}},
        "continuity_journal_entry": {"recovered": True},
    }
)

_NESTED_PROSE_JSON = json.dumps(
    {
        "action_type": None,
        "action_inputs": {},
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": {
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
            "rationale": "Keep the authored resolution rows and record why this move earns the next close.",
            "operator_progress_message": "Updating the resolution graph from the already-authored patch.",
        },
        "continuity_journal_entry": {"note": "kept at root"},
    }
)

_BANNED_DOMAIN_TERMS = (
    "transcript_edit",
    "transcript-edit",
    "deed_to_ir",
    "deed-to-ir",
    "deed to ir",
)


class _RawIoRecorder:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def observe_llm_io(self, record: dict[str, Any]) -> None:
        self._sink.append(dict(record))


class _RecordingSessionManager(ExecutionSessionManager):
    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs={"step_ref": f"artifact://{request.action_id}"}),
                budgets_remaining={},
                last_refusal=None,
            ),
        )


def _adapter(caller) -> LlmTurnOrchestrationAdapter:
    return LlmTurnOrchestrationAdapter(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="test prompt block"),),
            surface_payloads={},
            tool_handlers={"noop": lambda payload: payload},
        ),
        text_model_caller=caller,
        model_name="fake-model",
    )


def _orch_context(*, iterations: int = 1, raw_llm_io_observer: Any = None) -> OrchestratorContext:
    lm = LoopMemoryState()
    lm.iterations = iterations
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-contract-recovery",
        loop_memory=lm,
        request_id_prefix="req-contract-recovery",
        opaque_run_context={},
        raw_llm_io_observer=raw_llm_io_observer,
    )


def _phase_tracking_caller(responses: list[Any]):
    calls: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> Any:
        del model
        call_options = kwargs.get("call_options")
        calls.append({"prompt": prompt, "phase": getattr(call_options, "phase", None)})
        index = len(calls) - 1
        if index >= len(responses):
            return responses[-1]
        return responses[index]

    return caller, calls


def test_eligibility_requires_model_repair_still_invalid() -> None:
    assert is_recoverable_post_repair_contract_failure(
        original_reason_code="invalid_model_action_json",
        repair_method="model",
        repair_parse_ok=False,
        repair_parse_reason_code="invalid_model_action_json",
    )
    assert not is_recoverable_post_repair_contract_failure(
        original_reason_code="invalid_model_action_json",
        repair_method="deterministic_structure",
        repair_parse_ok=False,
        repair_parse_reason_code="invalid_model_action_json",
    )
    assert not is_recoverable_post_repair_contract_failure(
        original_reason_code="invalid_model_action_json",
        repair_method="model",
        repair_parse_ok=False,
        repair_parse_reason_code="model_caller_exception",
    )
    assert not is_recoverable_output_failure(
        reason_code="invalid_model_action_json",
        raw_response="not-json",
        raw_response_text="not-json",
    )


def test_adapter_raises_recoverable_turn_failure_after_failed_model_repair() -> None:
    records: list[dict[str, Any]] = []
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        return _CONTRACT_INVALID_JSON

    adapter = _adapter(caller)
    ctx = _orch_context(raw_llm_io_observer=_RawIoRecorder(records))

    with pytest.raises(RecoverableTurnFailure) as exc_info:
        adapter.choose_action(ctx, projection=None)

    assert len(calls) == 2
    failure = exc_info.value.failure_record
    assert failure["reason_code"] == "invalid_model_action_json"
    assert failure["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE
    assert failure["iteration"] == 1
    assert failure["prompt_mode"] == "full_choose_action"
    assert "rationale" in str(failure["parse_error_preview"])
    assert "parse_error_detail" not in failure
    assert "message" not in failure
    assert failure["repair_parse_reason_code"] == "invalid_model_action_json"
    assert failure["repair_method"] == "model"
    assert "repair_transformations" not in failure
    assert failure["original_action_count_attempted"] == 1
    _assert_bounded_json_native_failure_record(failure)
    assert "raw_prompt_text" not in failure
    assert "raw_llm_response_text" not in failure
    assert "raw_llm_response_tail" not in failure
    assert "repair_prompt_text" not in failure
    fb = ctx.loop_memory.contract_feedback
    assert fb["repair_attempted"] is True
    assert fb["repair_outcome"] == "failed"
    assert len(records) == 1
    rec = records[0]
    assert rec["parse_ok"] is False
    assert rec["parse_reason_code"] == "invalid_model_action_json"
    assert rec["repair_attempted"] is True
    assert rec["repair_parse_ok"] is False
    assert rec["repair_records"][0]["repair_parse_reason_code"] == "invalid_model_action_json"
    assert rec["recovery_disposition"] == QUEUED_TURN_RECOVERY_DISPOSITION


def test_orchestrator_recovers_from_post_repair_contract_failure() -> None:
    caller, calls = _phase_tracking_caller(
        [_CONTRACT_INVALID_JSON, _CONTRACT_INVALID_JSON, _VALID_DISPATCH_JSON, _VALID_COMPLETE_JSON]
    )
    checkpoints: list[dict[str, Any]] = []
    sm = _RecordingSessionManager()
    mem = LoopMemoryState()
    mem.continuity.mission_state = new_mission_state(
        mission_id="m-contract",
        loop_family="orchestration_kernel",
        objective="keep the seeded objective",
    )
    mem.continuity.resolution_state = new_resolution_state()
    mem.continuity.latest_refs = {"seed": "ref://seed"}

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=sm,
        session_id="s-contract-recovery",
        run_artifact_ref=None,
        request_id_prefix="r-contract-recovery",
        opaque_run_context={"recoverable_turn_failure_budget": 2},
        max_iterations=4,
        initial_loop_memory=mem,
        lifecycle=OrchestrationLifecycle(resume_checkpoint_writer=lambda snap: checkpoints.append(dict(snap))),
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert [call["phase"] for call in calls] == [
        "choose_action",
        "choose_action_repair",
        "choose_action_turn_recovery",
        "choose_action",
    ]
    assert '"prompt_mode": "turn_recovery"' in calls[2]["prompt"]
    assert len(sm.steps) == 1
    assert sm.steps[0].action_id == "noop"
    failed_checkpoint = checkpoints[0]
    assert failed_checkpoint["turn_recovery"]["last_failure"]["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE
    assert failed_checkpoint["continuity"]["latest_refs"] == {"seed": "ref://seed"}
    assert failed_checkpoint["continuity"]["mission_state"]["objective"] == "keep the seeded objective"
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["last_failure"] == {}
    assert result.kernel_resume_snapshot["turn_recovery"]["consecutive_failures"] == 0


def test_deterministic_structure_repair_does_not_enter_turn_recovery() -> None:
    caller, calls = _phase_tracking_caller([_NESTED_PROSE_JSON])
    sm = _RecordingSessionManager()

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=sm,
        session_id="s-deterministic",
        run_artifact_ref=None,
        request_id_prefix="r-deterministic",
        max_iterations=1,
    )

    assert [call["phase"] for call in calls] == ["choose_action"]
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["last_failure"] == {}
    assert not sm.steps


def test_successful_model_repair_does_not_enter_turn_recovery() -> None:
    caller, calls = _phase_tracking_caller(["not-json", _VALID_COMPLETE_JSON])

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-model-repair",
        run_artifact_ref=None,
        request_id_prefix="r-model-repair",
        max_iterations=2,
    )

    assert result.terminal_class == "completed"
    assert [call["phase"] for call in calls] == ["choose_action", "choose_action_repair"]
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["last_failure"] == {}


def test_repeated_contract_failures_honor_existing_budget() -> None:
    caller, calls = _phase_tracking_caller([_CONTRACT_INVALID_JSON])
    sm = _RecordingSessionManager()

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=sm,
        session_id="s-budget",
        run_artifact_ref=None,
        request_id_prefix="r-budget",
        max_iterations=8,
    )

    assert result.terminal_class == "failed"
    assert result.reason_code == "recoverable_turn_failure_budget_exhausted"
    assert [call["phase"] for call in calls] == [
        "choose_action",
        "choose_action_repair",
        "choose_action_turn_recovery",
        "choose_action_repair",
        "choose_action_turn_recovery",
        "choose_action_repair",
    ]
    assert not sm.steps
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["consecutive_failures"] == 3


def test_recovery_budget_zero_terminates_after_first_post_repair_failure() -> None:
    caller, calls = _phase_tracking_caller([_CONTRACT_INVALID_JSON])
    sm = _RecordingSessionManager()

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=sm,
        session_id="s-budget-zero",
        run_artifact_ref=None,
        request_id_prefix="r-budget-zero",
        opaque_run_context={"recoverable_turn_failure_budget": 0},
        max_iterations=4,
    )

    assert result.terminal_class == "failed"
    assert result.reason_code == "recoverable_turn_failure_budget_exhausted"
    assert [call["phase"] for call in calls] == ["choose_action", "choose_action_repair"]
    assert not sm.steps
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["consecutive_failures"] == 1


def test_successful_canonical_turn_resets_consecutive_recovery_failures() -> None:
    caller, calls = _phase_tracking_caller(
        [_CONTRACT_INVALID_JSON, _CONTRACT_INVALID_JSON, _VALID_COMPLETE_JSON]
    )

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-reset",
        run_artifact_ref=None,
        request_id_prefix="r-reset",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=4,
    )

    assert result.terminal_class == "completed"
    assert result.reason_code == "complete_run"
    assert [call["phase"] for call in calls] == [
        "choose_action",
        "choose_action_repair",
        "choose_action_turn_recovery",
    ]
    assert result.kernel_resume_snapshot is not None
    assert result.kernel_resume_snapshot["turn_recovery"]["consecutive_failures"] == 0
    assert result.kernel_resume_snapshot["turn_recovery"]["last_failure"] == {}


def test_checkpoint_resume_preserves_pending_contract_recovery_state() -> None:
    fail_caller, _fail_calls = _phase_tracking_caller([_CONTRACT_INVALID_JSON])
    first = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(fail_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-resume-1",
        run_artifact_ref=None,
        request_id_prefix="r-resume-1",
        max_iterations=1,
    )
    snapshot = first.kernel_resume_snapshot
    assert snapshot is not None
    last_failure = snapshot["turn_recovery"]["last_failure"]
    assert last_failure["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE
    assert last_failure["reason_code"] == "invalid_model_action_json"
    restored, next_iteration, err = parse_kernel_resume_snapshot(snapshot)
    assert err is None
    assert restored.turn_recovery.has_pending_recovery()
    assert restored.turn_recovery.last_failure["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE

    resume_caller, resume_calls = _phase_tracking_caller([_VALID_COMPLETE_JSON])
    second = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(resume_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-resume-2",
        run_artifact_ref=None,
        request_id_prefix="r-resume-2",
        max_iterations=2,
        initial_loop_memory=restored,
        resume_start_iteration=next_iteration,
    )
    assert resume_calls[0]["phase"] == "choose_action_turn_recovery"
    assert '"prompt_mode": "turn_recovery"' in resume_calls[0]["prompt"]
    assert second.terminal_class == "completed"
    assert second.kernel_resume_snapshot is not None
    assert second.kernel_resume_snapshot["turn_recovery"]["last_failure"] == {}


def test_length_failure_still_recovers_without_model_repair() -> None:
    caller, calls = _phase_tracking_caller(
        [
            {
                "success": False,
                "error": "OpenAI returned truncated response (finish_reason: length)",
                "text": None,
                "finish_reason": "length",
                "usage": {"prompt_tokens": 10, "completion_tokens": 16, "total_tokens": 26},
                "char_count": 0,
            },
            _VALID_COMPLETE_JSON,
        ]
    )

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-length",
        run_artifact_ref=None,
        request_id_prefix="r-length",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=3,
    )

    assert result.terminal_class == "completed"
    assert [call["phase"] for call in calls] == ["choose_action", "choose_action_turn_recovery"]


def test_content_filter_transport_and_repair_exception_do_not_use_contract_recovery() -> None:
    def content_filter_caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        del prompt, model
        return {
            "success": False,
            "error": "Provider blocked response (finish_reason: content_filter)",
            "text": None,
            "finish_reason": "content_filter",
        }

    with pytest.raises(ModelActionParseError):
        _adapter(content_filter_caller).choose_action(_orch_context(), projection=None)

    def transport_caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        del prompt, model
        return {"success": False, "error": "Connection error."}

    with pytest.raises(ResumableModelInterruption):
        _adapter(transport_caller).choose_action(_orch_context(), projection=None)

    calls: list[str] = []

    def repair_exception_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        if len(calls) == 1:
            return "not-json"
        raise RuntimeError("repair caller exploded")

    with pytest.raises(ModelActionParseError) as exc_info:
        _adapter(repair_exception_caller).choose_action(_orch_context(), projection=None)
    assert exc_info.value.reason_code == "model_caller_exception"
    assert len(calls) == 2


def test_turn_recovery_instruction_covers_truncation_and_contract_invalid() -> None:
    text = TURN_RECOVERY_INSTRUCTION.lower()
    assert "truncated" in text
    assert "empty" in text
    assert "contract-invalid after repair" in text
    assert "bounded failed-turn metadata" in text
    assert "smallest valid action-plan json" in text
    assert "do not reconstruct or copy the failed action object" in text
    assert "that object is the failure" in text
    for banned in _BANNED_DOMAIN_TERMS:
        assert banned not in text


def test_turn_recovery_prompt_projection_stays_generic() -> None:
    context = _orch_context(iterations=2)
    context.loop_memory.turn_recovery.record_failure(
        {
            "iteration": 1,
            "prompt_mode": "full_choose_action",
            "reason_code": "invalid_model_action_json",
            "failure_stage": POST_REPAIR_PARSE_FAILURE_STAGE,
        }
    )
    doc = build_turn_recovery_prompt_document(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="generic doctrine"),),
            surface_payloads={},
            tool_handlers={"noop": lambda payload: payload},
        ),
        opaque_launch_context={},
        context=context,
        projection=None,
        journal_verbatim_keep_n=1,
    )
    blob = (doc.prompt_text + json.dumps(doc.prompt_body, default=str)).lower()
    for banned in _BANNED_DOMAIN_TERMS:
        assert banned not in blob
    assert "contract-invalid after repair" in doc.instruction_text.lower()
    assert "smallest valid action-plan json" in doc.instruction_text.lower()
    assert "turn_recovery" in json.dumps(doc.prompt_body)


_HUGE_UNKNOWN_KEY = "k" * 50_000
_HUGE_PROVIDER_MODEL = "m" * 50_000
_HUGE_FINISH_REASON = "f" * 50_000


def _assert_bounded_json_native_failure_record(record: dict[str, Any]) -> None:
    payload = {key: value for key, value in record.items() if key != "consecutive_failures"}
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    assert compact_failure_record_size(payload) <= FAILURE_RECORD_COMPACT_JSON_CAP
    assert "parse_error_detail" not in payload
    assert "message" not in payload


def _assert_runner_checkpoint_serializable(snapshot: dict[str, Any]) -> str:
    return json.dumps(dict(snapshot), ensure_ascii=False, indent=2, sort_keys=True)


def _prompt_body_from_call(prompt: str) -> dict[str, Any]:
    marker = "\n\n{"
    index = prompt.find(marker)
    assert index >= 0
    return json.loads(prompt[index + 2 :])


def _assert_bounded_recovery_prompt(prompt: str, *, sentinel: str) -> dict[str, Any]:
    assert sentinel not in prompt
    body = _prompt_body_from_call(prompt)
    assert body.get("prompt_mode") == "turn_recovery"
    run_context = body.get("run_context")
    assert isinstance(run_context, dict)
    assert "contract_feedback" not in run_context
    turn_recovery = run_context.get("turn_recovery")
    assert isinstance(turn_recovery, dict)
    last_failure = turn_recovery.get("last_failure")
    assert isinstance(last_failure, dict)
    _assert_bounded_json_native_failure_record(last_failure)
    assert sentinel not in json.dumps(turn_recovery, ensure_ascii=False)
    return body


def _plan_with_huge_unknown_key() -> str:
    payload = json.loads(_CONTRACT_INVALID_JSON)
    payload[_HUGE_UNKNOWN_KEY] = True
    return json.dumps(payload)


def _fat_optional_repair_attempt() -> RepairAttempt:
    return RepairAttempt(
        repair_prompt_text="",
        repair_raw_response_text=_CONTRACT_INVALID_JSON,
        repair_parse_ok=False,
        repair_parse_reason_code="invalid_model_action_json",
        repair_parsed_action_plan=None,
        repair_error=ModelActionParseError("invalid_model_action_json", "still invalid"),
        repair_method=REPAIR_METHOD_MODEL,
        repair_transformations=tuple(f"t{index:02d}_" + ("x" * 60) for index in range(8)),
    )


def test_huge_unknown_action_plan_key_stays_bounded_on_checkpoint_and_recovery_prompt() -> None:
    huge_plan = _plan_with_huge_unknown_key()
    caller, calls = _phase_tracking_caller([huge_plan, huge_plan, _VALID_COMPLETE_JSON])
    checkpoints: list[dict[str, Any]] = []

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-huge-key",
        run_artifact_ref=None,
        request_id_prefix="r-huge-key",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(resume_checkpoint_writer=lambda snap: checkpoints.append(dict(snap))),
    )

    assert result.terminal_class == "completed"
    assert [call["phase"] for call in calls] == [
        "choose_action",
        "choose_action_repair",
        "choose_action_turn_recovery",
    ]
    last_failure = checkpoints[0]["turn_recovery"]["last_failure"]
    preview = str(last_failure.get("parse_error_preview") or "")
    assert preview.startswith("unexpected action plan keys:")
    assert len(preview) <= PARSE_ERROR_PREVIEW_CHARS
    assert last_failure["parse_error_char_count"] > PARSE_ERROR_PREVIEW_CHARS
    assert _HUGE_UNKNOWN_KEY not in preview
    _assert_bounded_json_native_failure_record(last_failure)
    dumped = _assert_runner_checkpoint_serializable(checkpoints[0])
    assert _HUGE_UNKNOWN_KEY not in dumped
    turn_recovery_blob = json.dumps(checkpoints[0]["turn_recovery"], ensure_ascii=False)
    assert _HUGE_UNKNOWN_KEY not in turn_recovery_blob
    _assert_bounded_recovery_prompt(calls[2]["prompt"], sentinel=_HUGE_UNKNOWN_KEY)


def test_uninterrupted_and_resumed_recovery_prompts_share_bounded_failure_lane() -> None:
    huge_plan = _plan_with_huge_unknown_key()

    live_caller, live_calls = _phase_tracking_caller([huge_plan, huge_plan, _VALID_COMPLETE_JSON])
    live = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(live_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-parity-live",
        run_artifact_ref=None,
        request_id_prefix="r-parity-live",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=3,
    )
    assert live.terminal_class == "completed"
    live_recovery = _assert_bounded_recovery_prompt(live_calls[2]["prompt"], sentinel=_HUGE_UNKNOWN_KEY)

    fail_caller, _fail_calls = _phase_tracking_caller([huge_plan])
    first = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(fail_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-parity-resume-1",
        run_artifact_ref=None,
        request_id_prefix="r-parity-resume-1",
        max_iterations=1,
    )
    snapshot = first.kernel_resume_snapshot
    assert snapshot is not None
    assert "contract_feedback" not in snapshot
    restored, next_iteration, err = parse_kernel_resume_snapshot(snapshot)
    assert err is None
    assert restored.contract_feedback == {}
    assert restored.turn_recovery.has_pending_recovery()

    resume_caller, resume_calls = _phase_tracking_caller([_VALID_COMPLETE_JSON])
    second = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(resume_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-parity-resume-2",
        run_artifact_ref=None,
        request_id_prefix="r-parity-resume-2",
        max_iterations=2,
        initial_loop_memory=restored,
        resume_start_iteration=next_iteration,
    )
    assert second.terminal_class == "completed"
    assert resume_calls[0]["phase"] == "choose_action_turn_recovery"
    resumed_recovery = _assert_bounded_recovery_prompt(resume_calls[0]["prompt"], sentinel=_HUGE_UNKNOWN_KEY)

    live_lane = live_recovery["run_context"]["turn_recovery"]["last_failure"]
    resumed_lane = resumed_recovery["run_context"]["turn_recovery"]["last_failure"]
    for key in (
        "reason_code",
        "failure_stage",
        "repair_method",
        "repair_parse_reason_code",
        "parse_error_preview",
        "parse_error_char_count",
    ):
        assert live_lane.get(key) == resumed_lane.get(key)


def test_repaired_contract_feedback_diagnostics_stay_bounded_on_next_prompt() -> None:
    huge_plan = _plan_with_huge_unknown_key()
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del model
        calls.append(prompt)
        return huge_plan if len(calls) == 1 else _VALID_COMPLETE_JSON

    adapter = _adapter(caller)
    ctx = _orch_context()
    plan = adapter.choose_action(ctx, projection=None)
    assert plan.complete_run is True
    feedback = ctx.loop_memory.contract_feedback
    assert feedback["repair_outcome"] == "repaired"
    assert "message" not in feedback
    assert len(str(feedback["message_preview"])) <= PARSE_ERROR_PREVIEW_CHARS
    assert int(feedback["message_char_count"]) > PARSE_ERROR_PREVIEW_CHARS
    assert _HUGE_UNKNOWN_KEY not in str(feedback["message_preview"])

    follow_up = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(
            blocks=(TurnBlock(content="generic doctrine"),),
            surface_payloads={},
            tool_handlers={"noop": lambda payload: payload},
        ),
        opaque_launch_context={},
        context=ctx,
        projection=None,
        journal_verbatim_keep_n=1,
    )
    assert "contract_feedback" in follow_up.prompt_body["run_context"]
    assert _HUGE_UNKNOWN_KEY not in follow_up.prompt_text
    projected = follow_up.prompt_body["run_context"]["contract_feedback"]
    assert "message" not in projected
    assert projected["message_preview"] == feedback["message_preview"]


def test_huge_provider_metadata_cannot_inflate_failure_record_or_recovery_prompt() -> None:
    envelope = {
        "success": True,
        "text": _CONTRACT_INVALID_JSON,
        "finish_reason": _HUGE_FINISH_REASON,
        "provider_model": _HUGE_PROVIDER_MODEL,
        "model": _HUGE_PROVIDER_MODEL,
        "api_model": "a" * 50_000,
        "usage": {
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "reasoning_tokens": 1,
            "total_tokens": 21,
        },
    }
    caller, calls = _phase_tracking_caller([envelope, envelope, _VALID_COMPLETE_JSON])
    checkpoints: list[dict[str, Any]] = []

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-huge-provider",
        run_artifact_ref=None,
        request_id_prefix="r-huge-provider",
        opaque_run_context={"recoverable_turn_failure_budget": 1},
        max_iterations=3,
        lifecycle=OrchestrationLifecycle(resume_checkpoint_writer=lambda snap: checkpoints.append(dict(snap))),
    )

    assert result.terminal_class == "completed"
    last_failure = checkpoints[0]["turn_recovery"]["last_failure"]
    assert "provider_model" not in last_failure
    assert "provider_finish_reason" not in last_failure
    assert "api_model" not in last_failure
    _assert_bounded_json_native_failure_record(last_failure)
    dumped = _assert_runner_checkpoint_serializable(checkpoints[0])
    assert _HUGE_PROVIDER_MODEL not in dumped
    assert _HUGE_FINISH_REASON not in dumped
    recovery_prompt = calls[2]["prompt"]
    assert _HUGE_PROVIDER_MODEL not in recovery_prompt
    assert _HUGE_FINISH_REASON not in recovery_prompt


def test_non_json_safe_provider_metadata_cannot_break_checkpoint_serialization() -> None:
    envelope = {
        "success": True,
        "text": _CONTRACT_INVALID_JSON,
        "finish_reason": {"stop", "length"},
        "provider_model": b"not-a-string-identity",
        "api_model": {"nested": True},
        "usage": {
            "prompt_tokens": {"prompt": 12},
            "completion_tokens": True,
            "reasoning_tokens": "8",
            "total_tokens": float("nan"),
        },
        "non_json_safe": {1, 2, 3},
    }
    fail_caller, _fail_calls = _phase_tracking_caller([envelope])
    first = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(fail_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-unsafe-meta-1",
        run_artifact_ref=None,
        request_id_prefix="r-unsafe-meta-1",
        max_iterations=1,
    )
    snapshot = first.kernel_resume_snapshot
    assert snapshot is not None
    last_failure = snapshot["turn_recovery"]["last_failure"]
    assert last_failure["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE
    assert "provider_model" not in last_failure
    assert "provider_finish_reason" not in last_failure
    assert "api_model" not in last_failure
    assert "provider_prompt_tokens" not in last_failure
    assert "provider_completion_tokens" not in last_failure
    assert "provider_reasoning_tokens" not in last_failure
    assert "provider_total_tokens" not in last_failure
    dumped = _assert_runner_checkpoint_serializable(snapshot)
    restored, next_iteration, err = parse_kernel_resume_snapshot(json.loads(dumped))
    assert err is None
    assert restored.turn_recovery.has_pending_recovery()
    assert restored.turn_recovery.last_failure["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE

    resume_caller, resume_calls = _phase_tracking_caller([_VALID_COMPLETE_JSON])
    second = run_orchestration_kernel_loop(
        orchestration_adapter=_adapter(resume_caller),
        session_manager=_RecordingSessionManager(),
        session_id="s-unsafe-meta-2",
        run_artifact_ref=None,
        request_id_prefix="r-unsafe-meta-2",
        max_iterations=2,
        initial_loop_memory=restored,
        resume_start_iteration=next_iteration,
    )
    assert resume_calls[0]["phase"] == "choose_action_turn_recovery"
    assert second.terminal_class == "completed"


def test_core_recovery_coordinates_survive_optional_field_omission() -> None:
    original = ModelActionParseError("invalid_model_action_json", "x" * 5_000)
    record = build_post_repair_contract_failure_record(
        original_exc=original,
        repair_attempt=_fat_optional_repair_attempt(),
        iteration=4,
        prompt_mode="full_choose_action",
        raw_response={
            "text": _CONTRACT_INVALID_JSON,
            "finish_reason": "f" * 80,
            "provider_model": "m" * 80,
            "api_model": "a" * 80,
            "usage": {
                "prompt_tokens": 11,
                "completion_tokens": 7,
                "reasoning_tokens": 2,
                "total_tokens": 20,
            },
        },
    )
    _assert_bounded_json_native_failure_record(record)
    for key in CORE_FAILURE_RECORD_KEYS:
        assert key in record
    assert record["reason_code"] == "invalid_model_action_json"
    assert record["failure_stage"] == POST_REPAIR_PARSE_FAILURE_STAGE
    assert record["iteration"] == 4
    assert record["prompt_mode"] == "full_choose_action"
    assert record["repair_method"] == "model"
    assert record["repair_parse_reason_code"] == "invalid_model_action_json"
    assert record["original_action_count_attempted"] == 1
    assert "repair_transformations" not in record
