from __future__ import annotations

import json
from typing import Any

import pytest

from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.continuity_journal import (
    kernel_turn_index_of,
    recent_step_records_for_prompt,
    wrap_journal_entry,
)
from harness.runtime.orchestration.contracts import OrchestratorContext
from harness.runtime.orchestration.trace_collector import KernelTraceCollector
from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.action_plan_parser import (
    ModelActionParseError,
    parse_action_plan_response as _coerce_action_plan,
)
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
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
                "rationale": None,
                "state_patch": {"resolution": {"active_item_id": "x"}},
                "continuity_journal_entry": {"patch_turn": True},
                "operator_progress_message": None,
            }
        ),
        available_tool_ids=("select_tool",),
    )
    assert plan.state_patch == {"resolution": {"active_item_id": "x"}}


def test_coerce_action_plan_rejects_non_object_state_patch() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": "nope",
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="state_patch must be"):
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
        continuity_compaction_prompt_char_threshold=kwargs.get("continuity_compaction_prompt_char_threshold"),
        continuity_compaction_trigger_fraction=kwargs.get("continuity_compaction_trigger_fraction"),
        continuity_compaction_max_prompt_chars=kwargs.get("continuity_compaction_max_prompt_chars"),
        continuity_journal_verbatim_keep_n=int(kwargs.get("continuity_journal_verbatim_keep_n", 5)),
    )


def _orch_context(*, iterations: int = 1) -> OrchestratorContext:
    lm = LoopMemoryState()
    lm.iterations = iterations
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-llm",
        loop_memory=lm,
        request_id_prefix="req-llm",
        opaque_run_context={},
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
                "rationale": None,
                "state_patch": None,
                "continuity_journal_entry": _LLM_CJ,
                "operator_progress_message": None,
            }
        )

    adapter = _minimal_llm_adapter(caller=caller)

    def cb(info: dict[str, Any]) -> None:
        payloads.append(dict(info))

    adapter.wire_identity_trace_cb(cb)
    ctx = _orch_context(iterations=2)
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

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.wire_identity_trace_cb(lambda info: payloads.append(dict(info)))
    ctx = _orch_context(iterations=1)

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
                "rationale": None,
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
    assert "status line for operator" in p
    assert "prior folded block" in p
    assert "turn_note" in p
    assert "recent_continuity_journal_entries" in p
    assert "recent_kernel_step_records" in p
    assert "recent_kernel_step_result_records" in p
    assert "skipped" in p


def test_run_continuity_pre_choose_action_invokes_compaction_llm_and_traces() -> None:
    calls: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        if "journal_entries_to_fold" in prompt:
            assert "kernel_step_result_records_to_fold" in prompt
            return json.dumps({"compacted_continuity_summary": "merged-from-model"})
        raise AssertionError("unexpected prompt branch")

    adapter = _minimal_llm_adapter(
        caller=caller,
        continuity_compaction_prompt_char_threshold=1,
        continuity_journal_verbatim_keep_n=2,
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
    adapter.run_continuity_pre_choose_action(ctx, None, tracer=tracer)
    assert ctx.loop_memory.continuity.compacted_continuity_summary == "merged-from-model"
    kinds = [e["event_kind"] for e in tracer.build_raw_events()]
    assert "continuity_compacted" in kinds
    assert len(calls) == 1
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

    adapter = _minimal_llm_adapter(
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
    adapter.run_continuity_pre_choose_action(ctx, None, tracer=tracer)
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

    adapter = _minimal_llm_adapter(
        caller=caller,
        continuity_compaction_trigger_fraction=0.99,
        continuity_journal_verbatim_keep_n=2,
    )
    ctx = _orch_context(iterations=3)
    ctx.loop_memory.continuity.continuity_journal_entries.append(
        wrap_journal_entry(kernel_turn_index=1, author_payload={"k": 1})
    )
    tracer = KernelTraceCollector(session_id="s-below", request_id="r-below")
    adapter.run_continuity_pre_choose_action(ctx, None, tracer=tracer)
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

    adapter = _minimal_llm_adapter(
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
    adapter.run_continuity_pre_choose_action(ctx, None, tracer=tracer)
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

    adapter = _minimal_llm_adapter(
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
    adapter.run_continuity_pre_choose_action(ctx, None, tracer=tracer)
    adapter.run_continuity_pre_choose_action(ctx, None, tracer=tracer)
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


def test_coerce_action_plan_rejects_null_continuity_journal_entry() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": None,
        "continuity_journal_entry": None,
        "operator_progress_message": None,
    }
    with pytest.raises(ModelActionParseError, match="continuity_journal_entry is required"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_empty_continuity_journal_entry() -> None:
    payload = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
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
        "rationale": None,
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
        "rationale": None,
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
        "rationale": None,
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
                "rationale": None,
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
    assert "shorthand" in captured[0].lower() or "normalizes" in captured[0].lower()


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
