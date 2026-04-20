from __future__ import annotations

import json
from typing import Any

import pytest

from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.continuity_journal import (
    kernel_turn_index_of,
    recent_step_records_for_prompt,
    wrap_journal_entry,
)
from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response as _coerce_action_plan,
)
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.llm_turn_lifecycle import LlmTurnPreChooseActionParticipant
from harness.runtime.orchestration.trace_collector import KernelTraceCollector
from harness.execution.session import ExecutionSessionManager

_LLM_CJ = {"llm_continuity_turn": True}


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
                "continuity_journal_entry": _LLM_CJ,
                "operator_progress_message": None,
                "hitl_request": {"message": "operator?", "choices": [], "context": {}},
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
                "rationale": "t",
                "state_patch": {"resolution": {"active_item_id": "x"}},
                "continuity_journal_entry": {"patch_turn": True},
                "operator_progress_message": None,
            }
        ),
        available_tool_ids=("select_tool",),
    )
    assert plan.state_patch == {"resolution": {"active_item_id": "x"}}


def test_coerce_action_plan_accepts_explicit_state_authoring_skip_turn() -> None:
    plan = _coerce_action_plan(
        json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-investigate",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": "First itemize the work and enter an investigation posture.",
                "state_patch": {
                    "mission": {"active_mode": "investigating"},
                    "resolution": {
                        "active_item_id": "item-1",
                        "items": [{"item_id": "item-1", "title": "Unverified claim", "kind": "open_question", "status": "open"}],
                    },
                },
                "continuity_journal_entry": {"investigation_turn": True},
                "operator_progress_message": "Clarifying investigation state.",
            }
        ),
        available_tool_ids=("select_tool",),
    )
    assert plan.action_type is None
    assert plan.skip_execution is True
    assert plan.state_patch is not None
    assert plan.state_patch["mission"]["active_mode"] == "investigating"


def test_coerce_action_plan_rejects_non_object_state_patch() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": "nope",
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="state_patch must be"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_accepts_null_action_type_with_state_patch_and_omitted_skip_execution() -> None:
    payload = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": {"mission": {"active_mode": "investigating"}},
        "continuity_journal_entry": _LLM_CJ,
    }
    plan = _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))
    assert plan.action_type is None
    assert plan.skip_execution is True
    assert plan.state_patch == {"mission": {"active_mode": "investigating"}}


def test_coerce_action_plan_rejects_null_action_type_without_state_patch() -> None:
    payload = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="state_patch or hitl_request is required when action_type is null on a no-dispatch turn"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_action_inputs_on_state_authoring_skip_turn() -> None:
    payload = {
        "action_type": None,
        "action_inputs": {"ref_ids": ["x"]},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": {"mission": {"active_mode": "investigating"}},
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="action_inputs must be empty when action_type is null on a no-dispatch turn"):
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
        "continuity_journal_entry": _LLM_CJ,
    }
    payload[field] = "false"

    with pytest.raises(ModelActionParseError, match=f"{field} must be a JSON boolean"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def _minimal_llm_adapter(**kwargs: Any) -> LlmTurnOrchestrationAdapter:
    composed = ComposedTurnInput(
        blocks=(TurnBlock(content="block"),),
        surface_payloads={},
        tool_handlers={"noop": lambda x: x},
    )
    return LlmTurnOrchestrationAdapter(
        composed_input=composed,
        text_model_caller=kwargs["caller"],
        model_name=str(kwargs.get("model_name", "fake")),
        opaque_launch_context=dict(kwargs.get("opaque") or {}),
        continuity_journal_verbatim_keep_n=int(kwargs.get("continuity_journal_verbatim_keep_n", 5)),
    )


def _minimal_pre_choose_action_participant(**kwargs: Any) -> LlmTurnPreChooseActionParticipant:
    composed = ComposedTurnInput(
        blocks=(TurnBlock(content="block"),),
        surface_payloads={},
        tool_handlers={"noop": lambda x: x},
    )
    return LlmTurnPreChooseActionParticipant(
        composed_input=composed,
        text_model_caller=kwargs["caller"],
        model_name=str(kwargs.get("model_name", "fake")),
        opaque_launch_context=dict(kwargs.get("opaque") or {}),
        continuity_compaction_prompt_char_threshold=kwargs.get("continuity_compaction_prompt_char_threshold"),
        continuity_compaction_trigger_fraction=kwargs.get("continuity_compaction_trigger_fraction"),
        continuity_compaction_max_prompt_chars=kwargs.get("continuity_compaction_max_prompt_chars"),
        continuity_journal_verbatim_keep_n=int(kwargs.get("continuity_journal_verbatim_keep_n", 5)),
        prompt_event_observer=kwargs.get("prompt_event_observer"),
    )


class _PromptEventRecorder:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def observe_prompt_event(self, info: dict[str, Any]) -> None:
        self._sink.append(dict(info))


class _RawIoRecorder:
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        self._sink = sink

    def observe_llm_io(self, record: dict[str, Any]) -> None:
        self._sink.append(dict(record))


def _orch_context(
    *,
    iterations: int = 1,
    prompt_event_observer: Any = None,
    raw_llm_io_observer: Any = None,
) -> OrchestratorContext:
    lm = LoopMemoryState()
    lm.iterations = iterations
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-llm",
        loop_memory=lm,
        request_id_prefix="req-llm",
        opaque_run_context={},
        prompt_event_observer=prompt_event_observer,
        raw_llm_io_observer=raw_llm_io_observer,
    )


def test_llm_turn_adapter_emits_one_prompt_event_per_successful_choose_action() -> None:
    payloads: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "ik-1",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": "t",
                "state_patch": None,
                "continuity_journal_entry": _LLM_CJ,
                "operator_progress_message": None,
            }
        )

    adapter = _minimal_llm_adapter(
        caller=caller,
    )
    ctx = _orch_context(
        iterations=2,
        prompt_event_observer=_PromptEventRecorder(payloads),
    )
    plan = adapter.choose_action(ctx, projection=None)
    assert plan.action_type == "noop"
    assert len(payloads) == 1
    assert payloads[0]["iteration"] == 2
    pe = payloads[0]["prompt_event"]
    assert pe["metadata"]["surface"] == "orchestration_kernel_llm_turn"
    assert pe["metadata"]["model"] == "fake"
    assert pe["metadata"]["prompt_char_count"] > 0
    assert pe["outcome_kind"] == "kernel_action_plan_parsed"
    assert pe["outcome_ref"] is None


def test_llm_turn_adapter_emits_parse_failed_prompt_event_before_raising() -> None:
    payloads: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return "not-json"

    adapter = _minimal_llm_adapter(
        caller=caller,
    )
    ctx = _orch_context(
        iterations=1,
        prompt_event_observer=_PromptEventRecorder(payloads),
    )

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(ctx, projection=None)

    assert len(payloads) == 1
    assert payloads[0]["prompt_event"]["outcome_kind"] == "kernel_action_plan_parse_failed"
    assert payloads[0]["prompt_event"]["outcome_ref"] == "invalid_model_action_json"


def test_choose_action_prompt_carries_prior_journal_progress_and_compacted_summary() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "ik-p",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": "t",
                "state_patch": None,
                "continuity_journal_entry": _LLM_CJ,
                "operator_progress_message": None,
            }
        )

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=2)
    ctx.loop_memory.continuity.continuity_journal_entries.append(
        wrap_journal_entry(kernel_turn_index=1, author_payload={"turn_note": "alpha"})
    )
    ctx.loop_memory.continuity.operator_progress_message = "status line for operator"
    ctx.loop_memory.continuity.compacted_continuity_summary = "prior folded block"
    ctx.loop_memory.continuity.kernel_step_records.append(
        {
            "kernel_turn_index": 1,
            "action_type": "noop",
            "skip_execution": True,
            "wait_for_human": False,
            "complete_run": False,
            "execution_state": "skipped",
            "execution_reason_code": None,
        }
    )
    adapter.choose_action(ctx, projection=None)
    assert len(captured) == 1
    p = captured[0]
    # operator_progress_message is no longer surfaced in default full_choose_action run_context.
    assert "status line for operator" not in p
    assert "prior folded block" in p
    assert "turn_note" in p
    assert "recent_continuity_journal_entries" in p
    assert "recent_turn_timeline" in p
    assert "recent_kernel_step_records" not in p
    assert "recent_kernel_step_result_records" not in p
    assert "skipped" in p


def test_pre_choose_action_participant_invokes_compaction_llm_and_traces() -> None:
    calls: list[str] = []
    payloads: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if "journal_entries_to_fold" in prompt:
            assert "kernel_step_result_records_to_fold" in prompt
            return json.dumps({"compacted_continuity_summary": "merged-from-model"})
        raise AssertionError("unexpected prompt branch")

    participant = _minimal_pre_choose_action_participant(
        caller=caller,
        continuity_compaction_prompt_char_threshold=1,
        continuity_journal_verbatim_keep_n=2,
        prompt_event_observer=_PromptEventRecorder(payloads),
    )
    ctx = _orch_context(iterations=3)
    for i in range(1, 6):
        ctx.loop_memory.continuity.continuity_journal_entries.append(
            wrap_journal_entry(kernel_turn_index=i, author_payload={"k": i})
        )
        ctx.loop_memory.continuity.kernel_step_records.append(
            {
                "kernel_turn_index": i,
                "action_type": "noop",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "skipped",
                "execution_reason_code": None,
            }
        )
    tracer = KernelTraceCollector(session_id="s-compact", request_id="r-compact")
    participant.before_choose_action(ctx, None, tracer=tracer)
    assert ctx.loop_memory.continuity.compacted_continuity_summary == "merged-from-model"
    kinds = [e["event_kind"] for e in tracer.build_raw_events()]
    assert "continuity_compacted" in kinds
    assert len(calls) == 1
    assert len(payloads) == 1
    assert payloads[0]["prompt_event"]["outcome_kind"] == "kernel_continuity_compaction_parsed"
    assert "journal_entries_to_fold" in calls[0]
    assert "kernel_step_result_records_to_fold" in calls[0]
    assert "target_compacted_summary_chars" in calls[0]


def test_run_continuity_occupancy_fraction_triggers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "harness.runtime.memory.continuity_compaction.resolve_context_window_tokens",
        lambda _m: (800, False),
    )

    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if "journal_entries_to_fold" in prompt:
            return json.dumps({"compacted_continuity_summary": "occ-merge"})
        raise AssertionError("unexpected prompt branch")

    participant = _minimal_pre_choose_action_participant(
        caller=caller,
        continuity_compaction_trigger_fraction=0.25,
        continuity_journal_verbatim_keep_n=2,
        model_name="gpt-5.4-mini",
    )
    ctx = _orch_context(iterations=3)
    for i in range(1, 6):
        ctx.loop_memory.continuity.continuity_journal_entries.append(
            wrap_journal_entry(kernel_turn_index=i, author_payload={"k": i})
        )
        ctx.loop_memory.continuity.kernel_step_records.append(
            {
                "kernel_turn_index": i,
                "action_type": "noop",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "skipped",
                "execution_reason_code": None,
            }
        )
    tracer = KernelTraceCollector(session_id="s-occ", request_id="r-occ")
    participant.before_choose_action(ctx, None, tracer=tracer)
    assert ctx.loop_memory.continuity.compacted_continuity_summary == "occ-merge"
    assert len(calls) == 1


def test_run_continuity_occupancy_fraction_does_not_trigger_when_below_threshold(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "harness.runtime.memory.continuity_compaction.resolve_context_window_tokens",
        lambda _m: (10_000_000, False),
    )

    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return json.dumps({"compacted_continuity_summary": "should-not-run"})

    participant = _minimal_pre_choose_action_participant(
        caller=caller,
        continuity_compaction_trigger_fraction=0.99,
        continuity_journal_verbatim_keep_n=2,
    )
    ctx = _orch_context(iterations=3)
    ctx.loop_memory.continuity.continuity_journal_entries.append(
        wrap_journal_entry(kernel_turn_index=1, author_payload={"k": 1})
    )
    tracer = KernelTraceCollector(session_id="s-below", request_id="r-below")
    participant.before_choose_action(ctx, None, tracer=tracer)
    assert calls == []
    assert ctx.loop_memory.continuity.compacted_continuity_summary is None


def test_run_continuity_fraction_with_unregistered_model_uses_250k_fallback_in_trace() -> None:
    """Real ``resolve_context_window_tokens`` (no monkeypatch): missing registry entry => 250k + fallback flag."""

    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if "journal_entries_to_fold" in prompt:
            return json.dumps({"compacted_continuity_summary": "fb-merge"})
        raise AssertionError("unexpected prompt branch")

    participant = _minimal_pre_choose_action_participant(
        caller=caller,
        continuity_compaction_trigger_fraction=0.005,
        continuity_journal_verbatim_keep_n=1,
        model_name="zzz-unknown-harness-model-id-99999",
    )
    ctx = _orch_context(iterations=2)
    for i in range(1, 25):
        ctx.loop_memory.continuity.continuity_journal_entries.append(
            wrap_journal_entry(kernel_turn_index=i, author_payload={"note": "x" * 400})
        )
        ctx.loop_memory.continuity.kernel_step_records.append(
            {"kernel_turn_index": i, "action_type": "noop", "execution_state": "skipped"}
        )
    tracer = KernelTraceCollector(session_id="s-fb", request_id="r-fb")
    participant.before_choose_action(ctx, None, tracer=tracer)
    assert ctx.loop_memory.continuity.compacted_continuity_summary == "fb-merge"
    assert len(calls) == 1
    evs = [e for e in tracer.build_raw_events() if e.get("event_kind") == "continuity_compacted"]
    assert evs and evs[0].get("payload", {}).get("used_context_window_fallback") is True


def test_second_compaction_does_not_resend_already_covered_turn_rows() -> None:
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if "journal_entries_to_fold" in prompt:
            return json.dumps({"compacted_continuity_summary": "updated"})
        raise AssertionError("unexpected prompt branch")

    participant = _minimal_pre_choose_action_participant(
        caller=caller,
        continuity_compaction_prompt_char_threshold=1,
        continuity_journal_verbatim_keep_n=2,
        continuity_compaction_max_prompt_chars=2600,
    )
    ctx = _orch_context(iterations=3)
    for i in range(1, 8):
        ctx.loop_memory.continuity.continuity_journal_entries.append(
            wrap_journal_entry(kernel_turn_index=i, author_payload={"tag": i})
        )
        ctx.loop_memory.continuity.kernel_step_records.append(
            {
                "kernel_turn_index": i,
                "action_type": "noop",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "skipped",
                "execution_reason_code": None,
            }
        )
        ctx.loop_memory.continuity.kernel_step_result_records.append(
            {
                "kernel_turn_index": i,
                "action_type": "noop",
                "execution_state": "executed",
                "execution_reason_code": None,
                "artifact_refs": [],
                "latest_refs_snapshot": {},
                "outputs_for_continuity": {},
                "result_truncated": False,
            }
        )
    tracer = KernelTraceCollector(session_id="s-wm", request_id="r-wm")
    participant.before_choose_action(ctx, None, tracer=tracer)
    participant.before_choose_action(ctx, None, tracer=tracer)
    assert len(calls) == 2
    assert '"tag": 1' in calls[0]
    assert '"tag": 1' not in calls[1]
    assert ctx.loop_memory.continuity.kernel_compaction_covered_through_turn_index >= 1


def test_partition_continuity_turn_aligned_when_journal_sparse() -> None:
    from harness.runtime.memory.continuity_journal import (
        partition_continuity_for_compaction,
        recent_journal_entries_for_prompt,
        wrap_journal_entry,
    )

    journal = [wrap_journal_entry(kernel_turn_index=2, author_payload={"only": 2})]
    steps = [
        {"kernel_turn_index": 1, "execution_state": "skipped"},
        {"kernel_turn_index": 2, "execution_state": "skipped"},
        {"kernel_turn_index": 3, "execution_state": "skipped"},
    ]
    j_fold, s_fold, r_fold = partition_continuity_for_compaction(journal, steps, [], keep_n=2)
    assert j_fold == []
    assert r_fold == []
    assert len(s_fold) == 1
    assert s_fold[0]["kernel_turn_index"] == 1
    recent = recent_journal_entries_for_prompt(journal, steps, [], keep_n=2)
    assert len(recent) == 1
    assert recent[0]["author_payload"]["only"] == 2
    rsteps = recent_step_records_for_prompt(journal, steps, [], keep_n=2)
    assert {kernel_turn_index_of(r) for r in rsteps} == {2, 3}


def test_verbatim_tail_unions_journal_step_and_result_layers() -> None:
    from harness.runtime.memory.continuity_journal import (
        recent_step_result_records_for_prompt,
        verbatim_turn_indices,
        wrap_journal_entry,
    )

    journal = [wrap_journal_entry(kernel_turn_index=1, author_payload={"a": 1})]
    steps: list[dict[str, Any]] = []
    results = [
        {
            "kernel_turn_index": 5,
            "action_type": "noop",
            "execution_state": "executed",
            "artifact_refs": [],
            "latest_refs_snapshot": {},
            "outputs_for_continuity": {},
            "result_truncated": False,
        }
    ]
    kept = verbatim_turn_indices(journal, steps, results, keep_n=2)
    assert kept == {1, 5}
    rrecent = recent_step_result_records_for_prompt(journal, steps, results, keep_n=2)
    assert len(rrecent) == 1
    assert rrecent[0]["kernel_turn_index"] == 5


def test_coerce_action_plan_accepts_null_continuity_journal_entry() -> None:
    # continuity_journal_entry is optional — null (omission) means no continuity delta this turn.
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": None,
        "operator_progress_message": None,
    }
    plan = _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))
    assert plan.continuity_journal_entry is None


def test_coerce_action_plan_rejects_empty_continuity_journal_entry() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": {},
        "operator_progress_message": None,
    }
    with pytest.raises(ModelActionParseError, match="non-empty"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_non_object_continuity_journal_entry() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": [],
        "operator_progress_message": None,
    }
    with pytest.raises(ModelActionParseError, match="continuity_journal_entry"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_wait_for_human_without_hitl_request() -> None:
    payload = {
        "action_type": "noop",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": True,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": _LLM_CJ,
        "operator_progress_message": None,
    }
    with pytest.raises(ModelActionParseError, match="hitl_request"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("noop",))


def test_coerce_action_plan_accepts_async_hitl_request() -> None:
    payload = {
        "action_type": "noop",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": _LLM_CJ,
        "operator_progress_message": None,
        "hitl_request": {"message": "heads up", "choices": [], "context": {}},
    }
    plan = _coerce_action_plan(json.dumps(payload), available_tool_ids=("noop",))
    assert plan.hitl_request is not None
    assert plan.hitl_request["message"] == "heads up"


def test_choose_action_prompt_includes_hitl_envelope_keys() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "ik-h",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "rationale": "t",
                "state_patch": None,
                "continuity_journal_entry": _LLM_CJ,
                "operator_progress_message": None,
            }
        )

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    ctx.loop_memory.hitl.pending_hitl_requests.append(
        {
            "prompt_id": "p-open",
            "message": "open",
            "choices": [],
            "context": {},
            "opaque_payload": {},
            "issued_at_iteration": 1,
        }
    )
    ctx.loop_memory.hitl.hitl_state = "async_prompts_pending"
    adapter.choose_action(ctx, projection=None)
    p = captured[0]
    assert "pending_hitl_requests" in p
    assert "answered_hitl_responses" in p
    assert "hitl_state" in p
    assert "p-open" in p


# ---------------------------------------------------------------------------
# Repair lane tests
# ---------------------------------------------------------------------------

_VALID_PLAN_JSON = json.dumps(
    {
        "action_type": "noop",
        "action_inputs": {},
        "idempotency_key": "ik-repair",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "repaired",
        "state_patch": None,
        "continuity_journal_entry": {"repair": True},
        "operator_progress_message": None,
    }
)

_VALID_STATE_AUTHORING_PLAN_JSON = json.dumps(
    {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-state-turn",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "First clarify the unresolved work before selecting another tool action.",
        "state_patch": {
            "mission": {"active_mode": "investigating"},
            "resolution": {
                "active_item_id": "item-1",
                "items": [{"item_id": "item-1", "title": "Unverified claim", "kind": "open_question", "status": "open"}],
            },
        },
        "continuity_journal_entry": {"repair": True, "investigation_turn": True},
        "operator_progress_message": "Clarifying investigation state.",
    }
)


def test_choose_action_repair_succeeds_on_second_attempt() -> None:
    """First call returns invalid JSON; second (repair) call returns valid JSON → plan returned."""
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "not-json"
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    plan = adapter.choose_action(ctx, projection=None)

    assert plan.action_type == "noop"
    assert len(calls) == 2
    # Second call should include the original prompt content and the repair instruction.
    assert "reason_code" in calls[1]
    assert "invalid_model_action_json" in calls[1]


def test_choose_action_repair_accepts_state_authoring_skip_turn() -> None:
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if len(calls) == 1:
            return "not-json"
        return _VALID_STATE_AUTHORING_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    plan = adapter.choose_action(ctx, projection=None)

    assert plan.action_type is None
    assert plan.skip_execution is True
    assert plan.state_patch is not None
    assert plan.state_patch["mission"]["active_mode"] == "investigating"
    assert len(calls) == 2


def test_choose_action_repair_sets_contract_feedback_on_success() -> None:
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json" if len(calls) == 1 else _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    fb = ctx.loop_memory.contract_feedback
    assert fb["repair_attempted"] is True
    assert fb["repair_outcome"] == "repaired"
    assert fb["reason_code"] == "invalid_model_action_json"


def test_choose_action_repair_fails_hard_on_second_failure() -> None:
    """Both calls return invalid JSON → raises ModelActionParseError."""
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json"

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(ctx, projection=None)

    assert len(calls) == 2
    fb = ctx.loop_memory.contract_feedback
    assert fb["repair_attempted"] is True
    assert fb["repair_outcome"] == "failed"


def test_choose_action_clean_turn_clears_contract_feedback() -> None:
    """A successful turn (no parse error) resets contract_feedback to empty dict."""

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    ctx.loop_memory.contract_feedback = {"repair_attempted": True, "repair_outcome": "repaired", "reason_code": "stale"}
    adapter.choose_action(ctx, projection=None)

    assert ctx.loop_memory.contract_feedback == {}


def test_choose_action_passes_json_object_call_options() -> None:
    """choose_action must pass call_options with output_mode='json_object' to the model caller."""
    from services.llm.call_options import LlmCallOptions

    received_opts: list[Any] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> str:
        received_opts.append(kwargs.get("call_options"))
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    assert len(received_opts) == 1
    opts = received_opts[0]
    assert isinstance(opts, LlmCallOptions)
    assert opts.output_mode == "json_object"
    assert opts.phase == "choose_action"


def test_choose_action_uses_resume_prompt_mode_when_hitl_answer_is_pending_integration() -> None:
    from services.llm.call_options import LlmCallOptions

    prompts: list[str] = []
    received_opts: list[Any] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> str:
        prompts.append(prompt)
        received_opts.append(kwargs.get("call_options"))
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=4)
    ctx.loop_memory.hitl.hitl_state = "answered_unintegrated"
    ctx.loop_memory.hitl.answered_hitl_responses.append(
        {"prompt_id": "p-1", "feedback": {"message": "continue north edge"}}
    )

    adapter.choose_action(ctx, projection=None)

    opts = received_opts[0]
    assert isinstance(opts, LlmCallOptions)
    assert opts.phase == "choose_action_resume"
    assert '"prompt_mode": "resume"' in prompts[0]
    assert "answered_hitl_responses" in prompts[0]


def test_choose_action_prompt_includes_contract_feedback_key() -> None:
    """contract_feedback must be present in the prompt envelope."""
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    ctx.loop_memory.contract_feedback = {"repair_attempted": True, "repair_outcome": "repaired"}
    adapter.choose_action(ctx, projection=None)

    assert "contract_feedback" in captured[0]
    assert "repair_outcome" in captured[0]


def test_choose_action_prompt_includes_summary_shorthand_explanation() -> None:
    """Prompt must explain that string values are valid shorthand for summary fields."""
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    assert "blocker_summary" in captured[0]
    assert "normalizes" in captured[0].lower()


def test_choose_action_prompt_includes_closure_state_contract() -> None:
    """Prompt must explain generic mission.closure_state support and dimension merging."""
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert "closure_state" in prompt
    assert "closure_state dimensions merge by `dimension_id`" in prompt
    assert "`closure_state shape:`" in prompt


def test_choose_action_prompt_explicitly_allows_state_authoring_skip_turns() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert "No-dispatch state-authoring turns are valid" in prompt
    assert "action_type` is absent or null" in prompt
    assert "Use only canonical `state_patch.mission` and `state_patch.resolution`" in prompt
    assert "record closure posture before dispatching another tool" not in prompt


def test_choose_action_prompt_teaches_commitment_after_item_exists() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    # Method/self-audit strings ("Once an actionable item exists", "normal next move is to take that check",
    # "what would have to be true in reality", "Do not use closed merely because...") moved to surface.py
    # doctrine blocks; they are not in the mechanical instruction text.
    # Mechanical instruction pins: state schema, success_conditions, completion_criteria still asserted here.
    assert "mission.success_conditions" in prompt
    assert "completion_criteria" in prompt
    assert "state_patch_feedback" in prompt  # observability/repair seam still in instruction
    assert "determination" in prompt  # present as field name in closure_state shape schema


def test_choose_action_prompt_includes_host_owned_prompt_observability_summary() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=4)
    ctx.loop_memory.telemetry.prompt_event_count = 7
    ctx.loop_memory.telemetry.last_prompt_event_id = "pe-7"
    ctx.loop_memory.telemetry.last_prompt_event_surface = "orchestration_kernel_llm_turn"
    ctx.loop_memory.continuity.kernel_step_records.extend(
        [
            {
                "kernel_turn_index": 1,
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {},
                "idempotency_key": "ik-1",
                "rationale": "load refs",
                "latest_refs_snapshot": {"working": "ref-1"},
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "executed",
                "execution_reason_code": None,
            },
            {
                "kernel_turn_index": 2,
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-2",
                "rationale": "record posture",
                "latest_refs_snapshot": {"working": "ref-1"},
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": False,
                "execution_state": "skipped",
                "execution_reason_code": None,
            },
        ]
    )
    ctx.loop_memory.continuity.state_patch_feedback = {
        "outcome": "rejected",
        "reason_code": "mission_unknown_keys",
    }
    ctx.loop_memory.continuity.resolution_state = new_resolution_state(
        items=[
            {
                "item_id": "i1",
                "title": "Thin closed item",
                "kind": "work_unit",
                "status": "closed",
            }
        ]
    )
    ctx.loop_memory.continuity.mission_state = new_mission_state(
        mission_id="m-proof",
        loop_family="orchestration_kernel",
        resolution_state=ctx.loop_memory.continuity.resolution_state,
        success_conditions=[
            {
                "condition_id": "c1",
                "title": "Mission reality condition",
                "status": "open",
            }
        ],
    )
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert '"prompt_observability_summary"' in prompt
    # Compact prompt-visible observability keeps structural anchors and
    # non-empty signals; broad zero/no-op counters are dropped from transport.
    assert '"last_state_patch_outcome": "rejected"' in prompt
    assert '"last_state_patch_reason_code": "mission_unknown_keys"' in prompt
    assert '"success_condition_count": 1' in prompt
    assert '"resolution_item_count": 1' in prompt
    assert '"work_universe_posture"' in prompt
    # Non-anchor count fields from the full summary are no longer surfaced.
    assert '"consecutive_no_dispatch_turns"' not in prompt
    assert '"turns_since_last_tool_execution"' not in prompt
    assert '"closed_items_without_basis_count"' not in prompt


def test_choose_action_prompt_hides_max_iterations_from_model_visible_launch_context() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(
        caller=caller,
        opaque={"run_id": "r1", "max_iterations": 99, "dossier_id": "d1"},
    )
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert '"run_id": "r1"' in prompt
    assert '"dossier_id": "d1"' in prompt
    assert "max_iterations" not in prompt


def test_choose_action_prompt_compacts_domain_closure_policy_to_requirements_only() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(
        caller=caller,
        opaque={
            "run_id": "r1",
            "domain_closure_policy": {
                "hard_enforced": True,
                "save_action_ids": ["save_workspace_artifact"],
                "publish_action_ids": ["publish_workspace_artifact"],
                "required_dimension_ids": ["layer_1"],
                "standards": [{"dimension_id": "layer_1", "question": "long semantic text"}],
            },
        },
    )
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert '"domain_closure_policy"' in prompt
    assert '"required_dimension_ids": ["layer_1"]' in prompt
    assert '"save_action_ids"' not in prompt
    assert '"publish_action_ids"' not in prompt
    assert '"standards"' not in prompt
    assert "long semantic text" not in prompt


def test_sync_projection_hides_max_iterations_from_mission_state_launch_context() -> None:
    adapter = _minimal_llm_adapter(
        caller=lambda *_args, **_kwargs: _VALID_PLAN_JSON,
        opaque={"run_id": "r2", "max_iterations": 7, "workspace_id": "w2"},
    )
    projection = adapter.sync(_orch_context(iterations=1))

    launch_context = projection.mission_state.opaque_payload["launch_context"]
    assert launch_context["run_id"] == "r2"
    assert launch_context["workspace_id"] == "w2"
    assert "max_iterations" not in launch_context


def test_choose_action_prompt_omits_projection_turn_snapshot_and_nested_launch_context() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller, opaque={"run_id": "r3", "workspace_id": "w3"})
    ctx = _orch_context(iterations=1)
    projection = adapter.sync(ctx)

    adapter.choose_action(ctx, projection=projection)

    prompt = captured[0]
    assert "turn_snapshot" not in prompt
    assert '"opaque_payload": {"launch_context"' not in prompt


def test_choose_action_prompt_uses_slim_tool_cards_in_surface_payloads() -> None:
    captured: list[str] = []
    valid_plan = json.dumps(
        {
            "action_type": "hydrate_artifact_refs",
            "action_inputs": {},
            "idempotency_key": "ik-1",
            "skip_execution": True,
            "wait_for_human": False,
            "complete_run": False,
            "rationale": "t",
            "state_patch": None,
            "continuity_journal_entry": _LLM_CJ,
            "operator_progress_message": None,
        }
    )

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return valid_plan

    composed = ComposedTurnInput(
        blocks=(TurnBlock(content="block"),),
        surface_payloads={
            "domain": {
                "domain": {
                    "tool_ids": ["hydrate_artifact_refs"],
                    "closure_policy": {"hard_enforced": True},
                    "tool_specs": [
                        {
                            "tool_id": "hydrate_artifact_refs",
                            "category": "read",
                            "purpose": "Load refs.",
                            "expected_request_shape": "ref_ids array",
                            "expected_request_json_shape": {"type": "object"},
                            "expected_result_shape": "big result blob",
                            "example_request": {"ref_ids": ["a"]},
                        }
                    ],
                }
            }
        },
        tool_handlers={"hydrate_artifact_refs": lambda x: x},
    )
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=composed,
        text_model_caller=caller,
        model_name="fake",
        opaque_launch_context={},
    )
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert '"tool_id": "hydrate_artifact_refs"' in prompt
    assert '"expected_request_shape": "ref_ids array"' in prompt
    assert "expected_request_json_shape" not in prompt
    assert "expected_result_shape" not in prompt
    assert "example_request" not in prompt
    assert '"closure_policy"' not in prompt


def test_choose_action_repair_preserves_image_attachments() -> None:
    """Repair call must carry forward image attachments from the original turn."""
    from services.llm.call_options import LlmCallOptions

    received_opts: list[Any] = []
    calls: list[str] = []

    def caller(prompt: str, model: str, **kwargs: Any) -> str:
        calls.append(prompt)
        received_opts.append(kwargs.get("call_options"))
        if len(calls) == 1:
            return "not-json"
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    # Simulate image evidence accumulated before choose_action is called.
    ctx.loop_memory.pending_image_evidence.append({"ref_id": "image:assoc:tx-1:original", "b64": "abc", "media_type": "image/png"})

    adapter.choose_action(ctx, projection=None)

    assert len(received_opts) == 2
    original_opts: LlmCallOptions = received_opts[0]
    repair_opts: LlmCallOptions = received_opts[1]

    # Both calls carry the same image attachments.
    assert len(original_opts.image_attachments) == 1
    assert original_opts.image_attachments[0]["ref_id"] == "image:assoc:tx-1:original"
    assert repair_opts.image_attachments == original_opts.image_attachments
    assert repair_opts.phase == "choose_action_repair"


# ---------------------------------------------------------------------------
# Non-repairable provider failure tests
# ---------------------------------------------------------------------------


def _provider_failure_response(error: str = "Connection error.") -> dict[str, Any]:
    """Return a failure response payload that triggers model_call_failed in the parser."""
    return {"success": False, "error": error}


def test_choose_action_provider_failure_does_not_trigger_repair() -> None:
    """model_call_failed must NOT issue a repair call — only one provider call is made."""
    calls: list[Any] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        calls.append(prompt)
        return _provider_failure_response()

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)

    with pytest.raises(ModelActionParseError) as exc_info:
        adapter.choose_action(ctx, projection=None)

    assert exc_info.value.reason_code == "model_call_failed"
    assert len(calls) == 1  # repair call must NOT have been issued


def test_choose_action_provider_failure_does_not_set_repair_contract_feedback() -> None:
    """contract_feedback must not carry repair_attempted=True for provider failures."""

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        return _provider_failure_response()

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(ctx, projection=None)

    fb = ctx.loop_memory.contract_feedback
    assert "repair_attempted" not in fb


def test_choose_action_provider_failure_emits_correct_observability() -> None:
    """Observability must reflect the provider failure reason code, not a repair outcome."""
    payloads: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        return _provider_failure_response("Connection error.")

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(
        iterations=1,
        prompt_event_observer=_PromptEventRecorder(payloads),
    )

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(ctx, projection=None)

    assert len(payloads) == 1
    pe = payloads[0]["prompt_event"]
    assert pe["outcome_kind"] == "kernel_action_plan_parse_failed"
    assert pe["outcome_ref"] == "model_call_failed"


def test_choose_action_json_failure_still_repairs() -> None:
    """Sanity: invalid_model_action_json still enters the repair lane after this change."""
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json" if len(calls) == 1 else _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    plan = adapter.choose_action(ctx, projection=None)

    assert plan.action_type == "noop"
    assert len(calls) == 2
    fb = ctx.loop_memory.contract_feedback
    assert fb["repair_attempted"] is True
    assert fb["repair_outcome"] == "repaired"


# ---------------------------------------------------------------------------
# Raw I/O audit observer
# ---------------------------------------------------------------------------


def test_choose_action_emits_raw_io_on_clean_success() -> None:
    """Clean turn: audit cb receives prompt, response, parse_ok=True, no repair."""
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.choose_action(
        _orch_context(iterations=3, raw_llm_io_observer=_RawIoRecorder(records)),
        projection=None,
    )

    assert len(records) == 1
    rec = records[0]
    assert rec["turn_index"] == 3
    assert rec["parse_ok"] is True
    assert rec["parse_reason_code"] is None
    assert rec["prompt_mode"] == "full_choose_action"
    assert rec["repair_attempted"] is False
    assert isinstance(rec["raw_prompt_text"], str) and len(rec["raw_prompt_text"]) > 0
    assert rec["raw_llm_response_char_count"] == len(_VALID_PLAN_JSON)
    assert rec["raw_llm_response_tail"] == _VALID_PLAN_JSON
    assert rec["provider_finish_reason"] is None
    assert rec["provider_total_tokens"] is None
    assert rec["provider_error"] is None
    assert "noop" in str(rec.get("parsed_action_plan") or "")


def test_choose_action_emits_raw_io_on_repair_success() -> None:
    """Repair path: audit cb reflects original failure + successful repair."""
    calls: list[str] = []
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json" if len(calls) == 1 else _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.choose_action(
        _orch_context(iterations=2, raw_llm_io_observer=_RawIoRecorder(records)),
        projection=None,
    )

    assert len(records) == 1
    rec = records[0]
    assert rec["turn_index"] == 2
    assert rec["parse_ok"] is False
    assert rec["parse_reason_code"] == "invalid_model_action_json"
    assert rec["repair_attempted"] is True
    assert rec["repair_parse_ok"] is True
    assert rec["repair_parse_reason_code"] is None


def test_choose_action_emits_raw_io_on_provider_failure() -> None:
    """Provider failure: audit cb reflects failure, no repair fields set."""
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        return {"success": False, "error": "Connection error."}

    adapter = _minimal_llm_adapter(caller=caller)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(
            _orch_context(iterations=1, raw_llm_io_observer=_RawIoRecorder(records)),
            projection=None,
        )

    assert len(records) == 1
    rec = records[0]
    assert rec["parse_ok"] is False
    assert rec["parse_reason_code"] == "model_call_failed"
    assert rec["repair_attempted"] is False


def test_choose_action_emits_provider_metadata_on_truncation_failure() -> None:
    """Provider-envelope facts should survive into raw I/O audit on truncation."""
    records: list[dict[str, Any]] = []
    partial_text = '{"action_type": "noop"'

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Provider returned truncated response (finish_reason: length)",
            "text": partial_text,
            "model": model,
            "finish_reason": "length",
            "usage": {
                "prompt_tokens": 12000,
                "completion_tokens": 20000,
                "reasoning_tokens": 7000,
                "total_tokens": 32000,
            },
            "char_count": len(partial_text),
            "provider_model": "provider-model-1",
            "api_model": "api-model-1",
        }

    adapter = _minimal_llm_adapter(caller=caller)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(
            _orch_context(iterations=1, raw_llm_io_observer=_RawIoRecorder(records)),
            projection=None,
        )

    assert len(records) == 1
    rec = records[0]
    assert rec["parse_ok"] is False
    assert rec["parse_reason_code"] == "model_call_failed"
    assert rec["repair_attempted"] is False
    assert rec["raw_llm_response_text"] == partial_text
    assert rec["raw_llm_response_char_count"] == len(partial_text)
    assert rec["raw_llm_response_tail"] == partial_text
    assert rec["provider_finish_reason"] == "length"
    assert rec["provider_prompt_tokens"] == 12000
    assert rec["provider_completion_tokens"] == 20000
    assert rec["provider_reasoning_tokens"] == 7000
    assert rec["provider_total_tokens"] == 32000
    assert rec["provider_error"] == "Provider returned truncated response (finish_reason: length)"
    assert rec["provider_model"] == "provider-model-1"
    assert rec["api_model"] == "api-model-1"


def test_choose_action_emits_provider_metadata_on_content_filter_failure() -> None:
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        return {
            "success": False,
            "error": "Provider blocked response (finish_reason: content_filter)",
            "text": None,
            "model": model,
            "finish_reason": "content_filter",
            "usage": {
                "prompt_tokens": 44,
                "completion_tokens": 55,
                "reasoning_tokens": None,
                "total_tokens": 99,
            },
            "char_count": 0,
            "provider_model": "provider-model-2",
            "api_model": "api-model-2",
        }

    adapter = _minimal_llm_adapter(caller=caller)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(
            _orch_context(iterations=1, raw_llm_io_observer=_RawIoRecorder(records)),
            projection=None,
        )

    rec = records[0]
    assert rec["parse_reason_code"] == "model_call_failed"
    assert rec["provider_finish_reason"] == "content_filter"
    assert rec["provider_prompt_tokens"] == 44
    assert rec["provider_completion_tokens"] == 55
    assert rec["provider_reasoning_tokens"] is None
    assert rec["provider_total_tokens"] == 99
    assert rec["provider_model"] == "provider-model-2"
    assert rec["api_model"] == "api-model-2"
    assert rec["raw_llm_response_text"] == "Provider blocked response (finish_reason: content_filter)"
    assert rec["raw_llm_response_char_count"] == len("Provider blocked response (finish_reason: content_filter)")


def test_choose_action_emits_provider_metadata_on_empty_response_failure() -> None:
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        return {
            "success": False,
            "error": "OpenAI returned empty text response",
            "text": None,
            "model": model,
            "finish_reason": "stop",
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 7,
                "reasoning_tokens": 1,
                "total_tokens": 17,
            },
            "char_count": 0,
            "provider_model": "provider-model-3",
            "api_model": "api-model-3",
        }

    adapter = _minimal_llm_adapter(caller=caller)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(
            _orch_context(iterations=1, raw_llm_io_observer=_RawIoRecorder(records)),
            projection=None,
        )

    rec = records[0]
    assert rec["parse_reason_code"] == "model_call_failed"
    assert rec["provider_finish_reason"] == "stop"
    assert rec["provider_prompt_tokens"] == 10
    assert rec["provider_completion_tokens"] == 7
    assert rec["provider_reasoning_tokens"] == 1
    assert rec["provider_total_tokens"] == 17
    assert rec["provider_model"] == "provider-model-3"
    assert rec["api_model"] == "api-model-3"
    assert rec["raw_llm_response_text"] == "OpenAI returned empty text response"
    assert rec["raw_llm_response_char_count"] == len("OpenAI returned empty text response")


def test_choose_action_works_with_no_raw_io_cb() -> None:
    """No cb wired → choose_action must succeed without error."""

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    plan = adapter.choose_action(_orch_context(iterations=1), projection=None)
    assert plan.action_type == "noop"


def test_raw_io_cb_exception_does_not_break_choose_action() -> None:
    """If the audit cb itself raises, choose_action must not propagate the error."""

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    class _ExplodingObserver:
        def observe_llm_io(self, record: dict[str, Any]) -> None:
            raise RuntimeError("audit observer exploded")

    adapter = _minimal_llm_adapter(caller=caller)
    plan = adapter.choose_action(
        _orch_context(iterations=1, raw_llm_io_observer=_ExplodingObserver()),
        projection=None,
    )
    assert plan.action_type == "noop"


# ---------------------------------------------------------------------------
# Repair I/O — full records in audit payload
# ---------------------------------------------------------------------------


def test_repair_audit_record_contains_prompt_and_response_texts() -> None:
    """Repair path: audit record carries full prompt/response text for the repair call."""
    calls: list[str] = []
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json" if len(calls) == 1 else _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.choose_action(
        _orch_context(iterations=4, raw_llm_io_observer=_RawIoRecorder(records)),
        projection=None,
    )

    assert len(records) == 1
    rec = records[0]
    assert rec["repair_attempted"] is True
    assert len(rec["repair_records"]) == 1
    rr = rec["repair_records"][0]
    assert "repair_prompt_text" in rr and len(rr["repair_prompt_text"]) > 0
    assert "repair_raw_response_text" in rr
    assert rr["repair_parse_ok"] is True
    assert rr["repair_parse_reason_code"] is None
    assert rr["repair_parsed_action_plan"]["action_type"] == "noop"


def test_repair_failed_audit_record_contains_reason_code() -> None:
    """Both repair attempts fail: record has repair_parse_ok=False and reason_code."""
    calls: list[str] = []
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json"  # always bad

    adapter = _minimal_llm_adapter(caller=caller)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(
            _orch_context(iterations=1, raw_llm_io_observer=_RawIoRecorder(records)),
            projection=None,
        )

    assert len(records) == 1
    rec = records[0]
    assert rec["repair_attempted"] is True
    rr = rec["repair_records"][0]
    assert rr["repair_parse_ok"] is False
    assert rr["repair_parse_reason_code"] == "invalid_model_action_json"
    assert rr["repair_parsed_action_plan"] is None


def test_clean_turn_has_empty_repair_records() -> None:
    """No repair on clean turn: repair_records is [] and repair_attempted is False."""
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.choose_action(
        _orch_context(iterations=1, raw_llm_io_observer=_RawIoRecorder(records)),
        projection=None,
    )

    rec = records[0]
    assert rec["repair_attempted"] is False
    assert rec["repair_records"] == []


# ---------------------------------------------------------------------------
# State before capture
# ---------------------------------------------------------------------------


def test_choose_action_audit_includes_state_before_snapshot() -> None:
    """Audit record must include mission_state_before, resolution_state_before, latest_refs_before."""
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(
        iterations=1,
        raw_llm_io_observer=_RawIoRecorder(records),
    )
    ctx.loop_memory.continuity.latest_refs = {"existing": "ref://x"}
    adapter.choose_action(ctx, projection=None)

    rec = records[0]
    assert "mission_state_before" in rec
    assert "resolution_state_before" in rec
    assert rec["latest_refs_before"] == {"existing": "ref://x"}


# ---------------------------------------------------------------------------
# Workstream 1: sparse continuity_journal_entry contract
# ---------------------------------------------------------------------------


def test_coerce_action_plan_accepts_omitted_continuity_journal_entry() -> None:
    """Missing continuity_journal_entry should parse as None — no error."""
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-sparse",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "sparse turn",
        "state_patch": None,
        # continuity_journal_entry intentionally omitted
        "operator_progress_message": None,
    }
    plan = _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))
    assert plan.continuity_journal_entry is None


def test_coerce_action_plan_rejects_empty_object_continuity_journal_entry() -> None:
    """An explicitly present but empty object should still be rejected."""
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": {},
        "operator_progress_message": None,
    }
    with pytest.raises(ModelActionParseError, match="non-empty"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_accepts_valid_continuity_journal_entry_when_present() -> None:
    """A present, non-empty object should be accepted and returned."""
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": "t",
        "state_patch": None,
        "continuity_journal_entry": {"step": "dispatching check"},
        "operator_progress_message": None,
    }
    plan = _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))
    assert plan.continuity_journal_entry == {"step": "dispatching check"}


# ---------------------------------------------------------------------------
# Workstream 3: _derive_repair_context structural derivation
# ---------------------------------------------------------------------------


def test_derive_repair_context_returns_none_for_non_json() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    obj, targets = _derive_repair_context("not-json", "some parse error")
    assert obj is None
    assert targets == []


def test_derive_repair_context_returns_none_for_json_array() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    obj, targets = _derive_repair_context("[1, 2, 3]", "some parse error")
    assert obj is None
    assert targets == []


def test_derive_repair_context_derives_missing_journal_target_when_error_references_it() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": None,
        "operator_progress_message": None,
        # continuity_journal_entry absent
    }
    obj, targets = _derive_repair_context(json.dumps(prior), "continuity_journal_entry is required")
    assert obj == prior
    assert "add_missing_continuity_journal_entry" in targets


def test_derive_repair_context_no_false_positive_for_absent_journal_unrelated_error() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": None,
        "operator_progress_message": None,
        # continuity_journal_entry absent, but error is unrelated
    }
    _, targets = _derive_repair_context(json.dumps(prior), "unknown action_type: bad_tool")
    # journal absence should NOT be surfaced when the error doesn't reference it
    assert "add_missing_continuity_journal_entry" not in targets


def test_derive_repair_context_derives_misplaced_closure_state_target() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": {
            "closure_state": {"overall_status": "open"},
            # no mission key
        },
        "operator_progress_message": None,
    }
    obj, targets = _derive_repair_context(json.dumps(prior), "some error")
    assert obj == prior
    assert "move_state_patch_closure_state_under_mission" in targets


def test_derive_repair_context_no_false_positive_unknown_key_on_invalid_action_type_error() -> None:
    """'unknown action_type: ...' errors must NOT trigger remove_unknown_top_level_keys."""
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior = {
        "action_type": "bad_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": None,
        "continuity_journal_entry": {"step": "ok"},
        "operator_progress_message": None,
    }
    _, targets = _derive_repair_context(json.dumps(prior), "unknown action_type: bad_tool")
    assert "remove_unknown_top_level_keys" not in targets


def test_derive_repair_context_triggers_unknown_key_target_on_unexpected_keys_error() -> None:
    """'unexpected action plan keys: ...' errors SHOULD trigger remove_unknown_top_level_keys."""
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": None,
        "continuity_journal_entry": {"step": "ok"},
        "operator_progress_message": None,
        "host_only_field": "should not be here",  # triggers the unexpected-key parse error
    }
    _, targets = _derive_repair_context(
        json.dumps(prior), "unexpected action plan keys: host_only_field"
    )
    assert "remove_unknown_top_level_keys" in targets


def test_derive_repair_context_no_false_positive_for_well_placed_closure_state() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "state_patch": {
            "mission": {
                "closure_state": {"overall_status": "open"},
            },
        },
        "continuity_journal_entry": {"step": "ok"},
        "operator_progress_message": None,
    }
    _, targets = _derive_repair_context(json.dumps(prior), "some unrelated error")
    assert "move_state_patch_closure_state_under_mission" not in targets


# ---------------------------------------------------------------------------
# should_use_state_repair_lane
# ---------------------------------------------------------------------------


def test_state_repair_lane_activates_on_rejected_feedback() -> None:
    from harness.runtime.orchestration.repair_lane import should_use_state_repair_lane
    assert should_use_state_repair_lane({"outcome": "rejected", "reason_code": "state_patch_unknown_keys"}) is True


def test_state_repair_lane_activates_on_applied_with_skipped_rows() -> None:
    from harness.runtime.orchestration.repair_lane import should_use_state_repair_lane
    assert should_use_state_repair_lane({"outcome": "applied", "skipped_resolution_rows": True}) is True


def test_state_repair_lane_does_not_activate_on_applied_without_skipped_rows() -> None:
    from harness.runtime.orchestration.repair_lane import should_use_state_repair_lane
    assert should_use_state_repair_lane({"outcome": "applied"}) is False
    assert should_use_state_repair_lane({"outcome": "applied", "skipped_resolution_rows": False}) is False


def test_state_repair_lane_does_not_activate_on_no_patch() -> None:
    from harness.runtime.orchestration.repair_lane import should_use_state_repair_lane
    assert should_use_state_repair_lane({"outcome": "no_patch"}) is False


def test_state_repair_lane_does_not_activate_on_none_feedback() -> None:
    from harness.runtime.orchestration.repair_lane import should_use_state_repair_lane
    assert should_use_state_repair_lane(None) is False
    assert should_use_state_repair_lane({}) is False
