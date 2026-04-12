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
        "rationale": None,
        "state_patch": "nope",
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="state_patch must be"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_null_action_type_without_skip_execution() -> None:
    payload = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": {"mission": {"active_mode": "investigating"}},
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="action_type is required unless completing, waiting, or authoring an explicit skip_execution state_patch turn"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_null_action_type_without_state_patch() -> None:
    payload = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": None,
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="state_patch is required when action_type is null on a skip_execution turn"):
        _coerce_action_plan(json.dumps(payload), available_tool_ids=("select_tool",))


def test_coerce_action_plan_rejects_action_inputs_on_state_authoring_skip_turn() -> None:
    payload = {
        "action_type": None,
        "action_inputs": {"ref_ids": ["x"]},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": {"mission": {"active_mode": "investigating"}},
        "continuity_journal_entry": _LLM_CJ,
    }
    with pytest.raises(ModelActionParseError, match="action_inputs must be empty when action_type is null on a skip_execution turn"):
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
    assert "closure_state dimensions merge by dimension_id" in prompt
    assert "generic run-level closure ledger" in prompt


def test_choose_action_prompt_explicitly_allows_state_authoring_skip_turns() -> None:
    captured: list[str] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        captured.append(prompt)
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    ctx = _orch_context(iterations=1)
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert "no-dispatch turn" in prompt
    assert "action_type null" in prompt
    assert "Do not emit mission or resolution as top-level keys" in prompt
    assert '"kind": "open_question"' in prompt
    assert "provisional investigation posture" in prompt
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
    assert "Once an actionable item exists" in prompt
    assert "normal next move is to take that check" in prompt
    assert "what would have to be true in reality" in prompt
    assert "Do not use closed merely because no contradiction has been noticed yet." in prompt
    assert '"determination" field on resolution items or closure dimensions' in prompt


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
    adapter.choose_action(ctx, projection=None)

    prompt = captured[0]
    assert '"prompt_observability_summary"' in prompt
    assert '"consecutive_no_dispatch_turns": 1' in prompt
    assert '"turns_since_last_tool_execution": 1' in prompt
    assert '"turns_since_latest_refs_change": 1' in prompt
    assert '"last_state_patch_outcome": "rejected"' in prompt


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
            "rationale": None,
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
    adapter.wire_identity_trace_cb(lambda info: payloads.append(dict(info)))
    ctx = _orch_context(iterations=1)

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
# Raw I/O audit callback (wire_raw_io_cb)
# ---------------------------------------------------------------------------


def test_choose_action_emits_raw_io_on_clean_success() -> None:
    """Clean turn: audit cb receives prompt, response, parse_ok=True, no repair."""
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.wire_raw_io_cb(records.append)
    adapter.choose_action(_orch_context(iterations=3), projection=None)

    assert len(records) == 1
    rec = records[0]
    assert rec["turn_index"] == 3
    assert rec["parse_ok"] is True
    assert rec["parse_reason_code"] is None
    assert rec["repair_attempted"] is False
    assert isinstance(rec["raw_prompt_text"], str) and len(rec["raw_prompt_text"]) > 0
    assert "noop" in str(rec.get("parsed_action_plan") or "")


def test_choose_action_emits_raw_io_on_repair_success() -> None:
    """Repair path: audit cb reflects original failure + successful repair."""
    calls: list[str] = []
    records: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        calls.append(prompt)
        return "not-json" if len(calls) == 1 else _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.wire_raw_io_cb(records.append)
    adapter.choose_action(_orch_context(iterations=2), projection=None)

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
    adapter.wire_raw_io_cb(records.append)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(_orch_context(iterations=1), projection=None)

    assert len(records) == 1
    rec = records[0]
    assert rec["parse_ok"] is False
    assert rec["parse_reason_code"] == "model_call_failed"
    assert rec["repair_attempted"] is False


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

    def bad_cb(data: dict[str, Any]) -> None:
        raise RuntimeError("audit cb exploded")

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.wire_raw_io_cb(bad_cb)
    plan = adapter.choose_action(_orch_context(iterations=1), projection=None)
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
    adapter.wire_raw_io_cb(records.append)
    adapter.choose_action(_orch_context(iterations=4), projection=None)

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
    adapter.wire_raw_io_cb(records.append)

    with pytest.raises(ModelActionParseError):
        adapter.choose_action(_orch_context(iterations=1), projection=None)

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
    adapter.wire_raw_io_cb(records.append)
    adapter.choose_action(_orch_context(iterations=1), projection=None)

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
    adapter.wire_raw_io_cb(records.append)
    ctx = _orch_context(iterations=1)
    ctx.loop_memory.continuity.latest_refs = {"existing": "ref://x"}
    adapter.choose_action(ctx, projection=None)

    rec = records[0]
    assert "mission_state_before" in rec
    assert "resolution_state_before" in rec
    assert rec["latest_refs_before"] == {"existing": "ref://x"}


# ---------------------------------------------------------------------------
# on_turn_completed wiring
# ---------------------------------------------------------------------------


def test_wire_turn_result_cb_and_on_turn_completed_delivers_data() -> None:
    """on_turn_completed fires turn_result_cb with expected keys."""
    results: list[dict[str, Any]] = []

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    adapter.wire_turn_result_cb(results.append)
    adapter.on_turn_completed(
        3,
        tool_request={"action_type": "noop"},
        tool_result_raw={"execution_state": "executed"},
        mission_state_after=None,
        resolution_state_after=None,
        latest_refs_after={"k": "v"},
        state_patch_feedback={},
        terminal_decision=None,
    )

    assert len(results) == 1
    r = results[0]
    assert r["turn_index"] == 3
    assert r["tool_request"]["action_type"] == "noop"
    assert r["latest_refs_after"] == {"k": "v"}


def test_on_turn_completed_with_no_cb_does_not_raise() -> None:
    """on_turn_completed must be safe to call with no turn_result_cb wired."""

    def caller(prompt: str, model: str, **_kwargs: Any) -> str:
        return _VALID_PLAN_JSON

    adapter = _minimal_llm_adapter(caller=caller)
    # No wire_turn_result_cb call — must not raise.
    adapter.on_turn_completed(
        1,
        tool_request=None,
        tool_result_raw=None,
        mission_state_after=None,
        resolution_state_after=None,
        latest_refs_after={},
        state_patch_feedback={},
        terminal_decision="complete_run",
    )


def test_turn_result_cb_exception_does_not_break_on_turn_completed() -> None:
    """If turn_result_cb raises, on_turn_completed must suppress it."""

    adapter = _minimal_llm_adapter(caller=lambda *a, **kw: _VALID_PLAN_JSON)
    adapter.wire_turn_result_cb(lambda _: (_ for _ in ()).throw(RuntimeError("boom")))
    # Should not raise.
    adapter.on_turn_completed(
        1,
        tool_request=None,
        tool_result_raw=None,
        mission_state_after=None,
        resolution_state_after=None,
        latest_refs_after={},
        state_patch_feedback={},
        terminal_decision=None,
    )
