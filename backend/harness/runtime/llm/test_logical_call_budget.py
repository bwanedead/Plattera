from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from harness.execution.executor import ExecutionExecutor
from harness.execution.contracts import ExecutionStepRequest
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.llm.logical_call_budget import (
    REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED,
    LogicalLlmCallBudget,
    LogicalLlmCallBudgetError,
    budget_from_wire,
    budget_model_caller,
    configure_logical_llm_call_budget,
    parse_env_max_llm_calls,
    parse_launch_max_llm_calls,
)
from harness.runtime.llm.provider_model_caller import ensure_provider_retry_model_caller
from harness.runtime.llm.instrumented_caller import instrument_model_caller
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import build_kernel_resume_snapshot, parse_kernel_resume_snapshot
from harness.runtime.orchestration.contracts import OrchestrationAdapter
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.composition import ComposedTurnInput
from harness.runtime.runner.runner import _with_delegate_subtask_tool
from services.llm.call_options import LlmCallOptions


def test_logical_budget_counts_parent_delegate_and_repair_calls_once_each() -> None:
    seen: list[str] = []

    def raw(_prompt: str, _model: str, *, call_options) -> dict:
        seen.append(call_options.phase)
        return {"text": "{}"}

    budget = LogicalLlmCallBudget(max_calls=3)
    caller = budget_model_caller(instrument_model_caller(raw), budget=budget)
    for phase in ("choose_action", "delegate_subtask", "action_plan_repair"):
        result = caller("p", "m", call_options=LlmCallOptions(phase=phase))
        assert result["llm_call_trace"]["logical_llm_call_number"] == len(seen)
        assert result["llm_call_trace"]["logical_llm_call_max"] == 3
    assert seen == ["choose_action", "delegate_subtask", "action_plan_repair"]
    assert budget.calls_used == 3


def test_logical_budget_prevents_call_after_exact_cap() -> None:
    raw_calls = 0

    def raw(_prompt: str, _model: str, **_kwargs) -> str:
        nonlocal raw_calls
        raw_calls += 1
        return "ok"

    caller = budget_model_caller(raw, budget=LogicalLlmCallBudget(max_calls=2))
    assert caller("p", "m") == "ok"
    assert caller("p", "m") == "ok"
    with pytest.raises(LogicalLlmCallBudgetError) as exc:
        caller("p", "m")
    assert exc.value.reason_code == REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED
    assert raw_calls == 2


def test_concurrent_reservations_never_admit_more_than_remaining_capacity() -> None:
    cap = 3
    provider_calls = 0
    provider_lock = Lock()
    admitted = Barrier(cap)

    def raw(_prompt: str, _model: str, **_kwargs) -> str:
        nonlocal provider_calls
        with provider_lock:
            provider_calls += 1
        admitted.wait(timeout=2)
        return "ok"

    budget = LogicalLlmCallBudget(max_calls=cap)
    caller = budget_model_caller(raw, budget=budget)

    def invoke() -> str:
        try:
            return caller("p", "m")
        except LogicalLlmCallBudgetError:
            return "exhausted"

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(lambda _: invoke(), range(8)))
    assert outcomes.count("ok") == cap
    assert outcomes.count("exhausted") == 5
    assert provider_calls == cap
    assert budget.calls_used == cap


def test_provider_transport_retries_consume_one_logical_budget_unit() -> None:
    provider_attempts = 0

    def provider(_prompt: str, _model: str, **_kwargs) -> dict:
        nonlocal provider_attempts
        provider_attempts += 1
        if provider_attempts == 1:
            return {"provider_request_failure": {"retryable": True}}
        return {"text": "ok"}

    budget = LogicalLlmCallBudget(max_calls=1)
    caller = budget_model_caller(ensure_provider_retry_model_caller(provider), budget=budget)
    result = caller("p", "m")
    assert isinstance(result, dict)
    assert result["text"] == "ok"
    assert result["retry_count_observed"] == 1
    assert provider_attempts == 2
    assert budget.calls_used == 1


def test_budget_is_durable_across_resume_and_fork_starts_a_new_run_count() -> None:
    memory = LoopMemoryState(logical_llm_call_budget=LogicalLlmCallBudget(max_calls=30, calls_used=12))
    resolution = new_resolution_state()
    memory.continuity.mission_state = new_mission_state(
        mission_id="m", loop_family="orchestration_kernel", resolution_state=resolution
    )
    memory.continuity.resolution_state = resolution
    manager = ExecutionSessionManager(executor=ExecutionExecutor())
    snapshot = build_kernel_resume_snapshot(
        loop_memory=memory, session_manager=manager, session_id="missing", next_iteration=4
    )
    restored, _, error = parse_kernel_resume_snapshot(snapshot)
    assert error is None
    assert restored.logical_llm_call_budget.to_wire() == {"max_calls": 30, "calls_used": 12}
    same_run, same_error = configure_logical_llm_call_budget(
        restored=restored.logical_llm_call_budget, configured_max_calls=30
    )
    assert same_error is None and same_run is not None and same_run.calls_used == 12
    fork_budget, fork_error = configure_logical_llm_call_budget(
        restored=restored.logical_llm_call_budget, configured_max_calls=30, reset_for_fork=True
    )
    assert fork_error is None and fork_budget is not None
    assert fork_budget.to_wire() == {"max_calls": 30, "calls_used": 0}


@pytest.mark.parametrize(
    "stored",
    [
        {"max_calls": True, "calls_used": 0},
        {"max_calls": 2, "calls_used": True},
        {"max_calls": -1, "calls_used": 0},
        {"max_calls": 2, "calls_used": 3},
        {"max_calls": 2},
    ],
)
def test_malformed_stored_budget_is_rejected_without_coercion(stored: object) -> None:
    budget, error = budget_from_wire(stored)
    assert budget is None
    assert error == "resume_snapshot_logical_llm_call_budget_invalid"


def test_malformed_budget_in_resume_snapshot_fails_closed() -> None:
    resolution = new_resolution_state()
    mission = new_mission_state(mission_id="m", loop_family="orchestration_kernel", resolution_state=resolution)
    snapshot = {
        "schema_version": "kernel_resume.v1",
        "next_iteration": 1,
        "continuity": {"latest_refs": {}, "mission_state": mission.model_dump(mode="json"), "resolution_state": resolution.model_dump(mode="json")},
        "hitl": {"hitl_state": "no_prompt"},
        "telemetry": {},
        "logical_llm_call_budget": {"max_calls": 30, "calls_used": "12"},
        "execution_session": None,
    }
    _, _, error = parse_kernel_resume_snapshot(snapshot)
    assert error == "resume_snapshot_logical_llm_call_budget_invalid"


@pytest.mark.parametrize("value", [True, "30", 1.5, -1])
def test_malformed_launch_budget_is_rejected_without_coercion(value: object) -> None:
    cap, error = parse_launch_max_llm_calls(value)
    assert cap is None
    assert error == "logical_llm_call_budget_invalid"
    assert parse_env_max_llm_calls("30")[0] == 30
    assert parse_env_max_llm_calls("+30")[1] == "logical_llm_call_budget_invalid"


def test_unset_budget_leaves_model_caller_unlimited() -> None:
    calls = 0

    def raw(_prompt: str, _model: str, **_kwargs) -> str:
        nonlocal calls
        calls += 1
        return "ok"

    caller = budget_model_caller(raw, budget=LogicalLlmCallBudget())
    for _ in range(31):
        assert caller("p", "m") == "ok"
    assert calls == 31


def test_composed_parallel_delegates_share_the_parent_and_repair_budget() -> None:
    provider_calls = 0
    provider_lock = Lock()
    delegate_admitted = Barrier(2)

    def raw(_prompt: str, _model: str, *, call_options) -> str:
        nonlocal provider_calls
        with provider_lock:
            provider_calls += 1
        if call_options.phase == DELEGATE_SUBTASK_ACTION_TYPE:
            delegate_admitted.wait(timeout=2)
            return json.dumps(
                {"status": "completed", "result": {"reading": "A", "ambiguity": "", "observations": [], "limits": []}}
            )
        return "{}"

    budget = LogicalLlmCallBudget(max_calls=4)
    shared_caller = budget_model_caller(raw, budget=budget)
    composed = _with_delegate_subtask_tool(
        ComposedTurnInput(blocks=(), tool_handlers={"seed": lambda _request: None}),
        model_caller=shared_caller,
        model_name="muse-spark-1.3-contributor",
    )
    delegate = composed.tool_handlers[DELEGATE_SUBTASK_ACTION_TYPE]
    assert shared_caller("parent", "m", call_options=LlmCallOptions(phase="choose_action")) == "{}"

    def invoke_delegate(index: int):
        return delegate(
            ExecutionStepRequest(
                session_id="s",
                action_id=DELEGATE_SUBTASK_ACTION_TYPE,
                inputs={
                    "profile": "harness.observation",
                    "task": "Read only the supplied local evidence.",
                    "context_refs": [f"artifact:{index}"],
                    "isolation": {"omit_parent_graph": True},
                },
                idempotency_key=f"delegate:{index}",
                run_id="r",
            )
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        delegate_results = list(pool.map(invoke_delegate, range(2)))
    assert sum(row.outputs["status"] == "completed" for row in delegate_results) == 2
    assert shared_caller("repair", "m", call_options=LlmCallOptions(phase="action_plan_repair")) == "{}"
    with pytest.raises(LogicalLlmCallBudgetError):
        shared_caller("parent", "m", call_options=LlmCallOptions(phase="choose_action"))
    assert provider_calls == 4
    assert budget.calls_used == 4


def test_delegate_budget_exhaustion_is_contained_until_parent_terminates() -> None:
    provider_calls = 0
    provider_lock = Lock()
    admitted = Barrier(1)

    def raw(_prompt: str, _model: str, *, call_options) -> str:
        nonlocal provider_calls
        with provider_lock:
            provider_calls += 1
        if call_options.phase == DELEGATE_SUBTASK_ACTION_TYPE:
            admitted.wait(timeout=2)
            return json.dumps(
                {"status": "completed", "result": {"reading": "A", "ambiguity": "", "observations": [], "limits": []}}
            )
        return "{}"

    budget = LogicalLlmCallBudget(max_calls=2)
    shared_caller = budget_model_caller(raw, budget=budget)
    composed = _with_delegate_subtask_tool(
        ComposedTurnInput(blocks=(), tool_handlers={"seed": lambda _request: None}),
        model_caller=shared_caller,
        model_name="muse-spark-1.3-contributor",
    )
    assert shared_caller("parent", "m", call_options=LlmCallOptions(phase="choose_action")) == "{}"
    delegate = composed.tool_handlers[DELEGATE_SUBTASK_ACTION_TYPE]
    request = ExecutionStepRequest(
        session_id="s",
        action_id=DELEGATE_SUBTASK_ACTION_TYPE,
        inputs={
            "profile": "harness.observation",
            "task": "Read only the supplied local evidence.",
            "context_refs": ["artifact:1"],
            "isolation": {"omit_parent_graph": True},
        },
        idempotency_key="delegate:1",
        run_id="r",
    )
    assert delegate(request).outputs["status"] == "completed"
    assert delegate(request).outputs["status"] == "failed"
    with pytest.raises(LogicalLlmCallBudgetError):
        shared_caller("next-parent", "m", call_options=LlmCallOptions(phase="choose_action"))
    assert provider_calls == 2
    assert budget.calls_used == 2


class _BudgetExhaustedAdapter(OrchestrationAdapter):
    def __init__(self, caller) -> None:
        self._caller = caller

    def initialize(self, context) -> None:
        del context

    def sync(self, context):
        del context
        return None

    def choose_action(self, context, projection):
        del context, projection
        return self._caller("prompt", "model")

    def evaluate_terminal(self, context, projection):
        del context, projection
        return None


def test_kernel_stops_cleanly_when_budget_is_exhausted_before_parent_call() -> None:
    provider_calls = 0

    def raw(_prompt: str, _model: str, **_kwargs) -> str:
        nonlocal provider_calls
        provider_calls += 1
        return json.dumps({})

    memory = LoopMemoryState(logical_llm_call_budget=LogicalLlmCallBudget(max_calls=0))
    result = run_orchestration_kernel_loop(
        orchestration_adapter=_BudgetExhaustedAdapter(budget_model_caller(raw, budget=memory.logical_llm_call_budget)),
        session_manager=ExecutionSessionManager(executor=ExecutionExecutor()),
        session_id="budget-session",
        run_artifact_ref=None,
        request_id_prefix="budget",
        max_iterations=3,
        initial_loop_memory=memory,
    )
    assert result.terminal_class == "exhausted"
    assert result.reason_code == REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED
    assert provider_calls == 0
    assert result.runtime_state["logical_llm_call_budget"] == {"max_calls": 0, "calls_used": 0}


def test_repair_exhaustion_propagates_to_the_terminal_budget_result() -> None:
    provider_calls = 0

    def raw(_prompt: str, _model: str, **_kwargs) -> str:
        nonlocal provider_calls
        provider_calls += 1
        return "not valid action JSON"

    memory = LoopMemoryState(logical_llm_call_budget=LogicalLlmCallBudget(max_calls=1))
    result = run_orchestration_kernel_loop(
        orchestration_adapter=LlmTurnOrchestrationAdapter(
            composed_input=ComposedTurnInput(blocks=()),
            text_model_caller=budget_model_caller(raw, budget=memory.logical_llm_call_budget),
            model_name="muse-spark-1.3-contributor",
        ),
        session_manager=ExecutionSessionManager(executor=ExecutionExecutor()),
        session_id="repair-budget-session",
        run_artifact_ref=None,
        request_id_prefix="repair-budget",
        max_iterations=2,
        initial_loop_memory=memory,
    )
    assert result.terminal_class == "exhausted"
    assert result.reason_code == REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED
    assert provider_calls == 1
    assert memory.logical_llm_call_budget.calls_used == 1


def test_compaction_uses_the_shared_budget_and_exhaustion_terminates() -> None:
    from harness.runtime.memory.continuity_journal import wrap_journal_entry
    from harness.runtime.orchestration.lifecycle import OrchestrationLifecycle
    from harness.runtime.orchestration.llm_turn_lifecycle import LlmTurnPreChooseActionParticipant

    provider_calls = 0
    phases: list[str] = []

    def raw(_prompt: str, _model: str, *, call_options) -> str:
        nonlocal provider_calls
        provider_calls += 1
        phases.append(call_options.phase)
        if call_options.phase == "continuity_compaction":
            return json.dumps({"compacted_continuity_summary": "folded"})
        return json.dumps(
            {
                "skip_execution": True,
                "complete_run": True,
                "rationale": "done",
                "continuity_journal_entry": {"ok": True},
                "state_patch": {
                    "mission": {
                        "objective": "Finish the assigned mission",
                        "success_conditions": [
                            {
                                "condition_id": "sc-1",
                                "title": "Named success condition",
                                "status": "open",
                            }
                        ],
                        "work_universe_posture": "audited",
                    }
                },
            }
        )

    budget = LogicalLlmCallBudget(max_calls=1)
    caller = budget_model_caller(raw, budget=budget)
    composed = ComposedTurnInput(blocks=())
    adapter = LlmTurnOrchestrationAdapter(
        composed_input=composed,
        text_model_caller=caller,
        model_name="muse-spark-1.3-contributor",
    )
    participant = LlmTurnPreChooseActionParticipant(
        composed_input=composed,
        text_model_caller=caller,
        model_name="muse-spark-1.3-contributor",
        continuity_compaction_prompt_char_threshold=1,
        continuity_journal_verbatim_keep_n=2,
    )
    memory = LoopMemoryState(logical_llm_call_budget=budget)
    for i in range(1, 6):
        memory.continuity.continuity_journal_entries.append(
            wrap_journal_entry(kernel_turn_index=i, author_payload={"k": i})
        )
        memory.continuity.kernel_step_records.append(
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
    result = run_orchestration_kernel_loop(
        orchestration_adapter=adapter,
        session_manager=ExecutionSessionManager(executor=ExecutionExecutor()),
        session_id="compaction-budget-session",
        run_artifact_ref=None,
        request_id_prefix="compaction-budget",
        max_iterations=2,
        initial_loop_memory=memory,
        lifecycle=OrchestrationLifecycle(pre_choose_action_participant=participant),
    )
    assert result.terminal_class == "exhausted"
    assert result.reason_code == REASON_LOGICAL_LLM_CALL_BUDGET_EXHAUSTED
    assert phases == ["continuity_compaction"]
    assert provider_calls == 1
    assert budget.calls_used == 1
    assert result.runtime_state["logical_llm_call_budget"] == {"max_calls": 1, "calls_used": 1}


def test_cli_cap_is_non_bypassable_ceiling(monkeypatch) -> None:
    from harness.runtime.runner.runner import _select_max_llm_calls

    monkeypatch.delenv("HARNESS_CLI_MAX_LLM_CALLS", raising=False)
    assert _select_max_llm_calls({}) == (None, None)
    assert _select_max_llm_calls({"max_llm_calls": None}) == (None, None)
    assert _select_max_llm_calls({"max_llm_calls": 10}) == (10, None)

    monkeypatch.setenv("HARNESS_CLI_MAX_LLM_CALLS", "30")
    assert _select_max_llm_calls({}) == (30, None)
    assert _select_max_llm_calls({"max_llm_calls": None}) == (30, None)
    assert _select_max_llm_calls({"max_llm_calls": 50}) == (30, None)
    assert _select_max_llm_calls({"max_llm_calls": 10}) == (10, None)


def test_malformed_budget_lanes_refuse_before_model_call(monkeypatch, tmp_path) -> None:
    from harness.runtime.composition import TurnSurface
    from harness.runtime.runner import RuntimeArtifactTargets, RuntimeRunner, RuntimeRunnerError

    provider_calls = 0

    def raw(_prompt: str, _model: str, **_kwargs) -> str:
        nonlocal provider_calls
        provider_calls += 1
        return "{}"

    class _Adapter:
        def build_turn_surface(self, launch_context: dict[str, object]) -> TurnSurface:
            return TurnSurface(surface_id="budget-surface", blocks=(), payload={})

    runner = RuntimeRunner(
        adapter=_Adapter(),
        model_caller=raw,
        targets=RuntimeArtifactTargets(done_file=tmp_path / "done.json", result_file=tmp_path / "result.json"),
    )

    monkeypatch.delenv("HARNESS_CLI_MAX_LLM_CALLS", raising=False)
    with pytest.raises(RuntimeRunnerError) as exc_info:
        runner.run(launch_context={"max_llm_calls": True, "run_id": "bad-budget-context"})
    assert "logical_llm_call_budget_invalid" in str(exc_info.value)
    assert provider_calls == 0

    monkeypatch.setenv("HARNESS_CLI_MAX_LLM_CALLS", "+30")
    with pytest.raises(RuntimeRunnerError) as exc_info:
        runner.run(launch_context={"run_id": "bad-budget-env"})
    assert "logical_llm_call_budget_invalid" in str(exc_info.value)
    assert provider_calls == 0

    from harness.runtime.runner.runner import _select_max_llm_calls

    monkeypatch.delenv("HARNESS_CLI_MAX_LLM_CALLS", raising=False)
    assert _select_max_llm_calls({"max_llm_calls": "30"})[1] == "logical_llm_call_budget_invalid"
    monkeypatch.setenv("HARNESS_CLI_MAX_LLM_CALLS", "+30")
    assert _select_max_llm_calls({"max_llm_calls": 10})[1] == "logical_llm_call_budget_invalid"


def test_same_run_resume_cannot_raise_or_remove_persisted_cap() -> None:
    restored = LogicalLlmCallBudget(max_calls=30, calls_used=12)
    kept, err = configure_logical_llm_call_budget(restored=restored, configured_max_calls=30)
    assert err is None and kept is not None
    assert kept.to_wire() == {"max_calls": 30, "calls_used": 12}

    omitted, omit_err = configure_logical_llm_call_budget(restored=restored, configured_max_calls=None)
    assert omit_err is None and omitted is not None
    assert omitted.to_wire() == {"max_calls": 30, "calls_used": 12}

    raised, raise_err = configure_logical_llm_call_budget(restored=restored, configured_max_calls=50)
    assert raised is None
    assert raise_err == "logical_llm_call_budget_resume_config_mismatch"

    lowered, lower_err = configure_logical_llm_call_budget(restored=restored, configured_max_calls=10)
    assert lowered is None
    assert lower_err == "logical_llm_call_budget_resume_config_mismatch"


def test_fork_retains_effective_ceiling_and_resets_usage_only() -> None:
    restored = LogicalLlmCallBudget(max_calls=30, calls_used=12)
    forked, err = configure_logical_llm_call_budget(
        restored=restored,
        configured_max_calls=30,
        reset_for_fork=True,
    )
    assert err is None and forked is not None
    assert forked.to_wire() == {"max_calls": 30, "calls_used": 0}

    forked_min, min_err = configure_logical_llm_call_budget(
        restored=LogicalLlmCallBudget(max_calls=50, calls_used=9),
        configured_max_calls=30,
        reset_for_fork=True,
    )
    assert min_err is None and forked_min is not None
    assert forked_min.to_wire() == {"max_calls": 30, "calls_used": 0}


def test_cli_accepts_max_llm_calls_thirty(monkeypatch, tmp_path) -> None:
    import harness.cli.start as cli_start

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    captured: dict[str, object] = {}

    def fake_start_run(**kwargs):
        captured.update(kwargs)
        return {"status": "started", "run_id": kwargs["run_id"]}

    monkeypatch.setattr(cli_start, "start_run", fake_start_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "harness.cli.start",
            "--loop-kind",
            "harness_cli",
            "--run-id",
            "budget-cli-30",
            "--max-llm-calls",
            "30",
            "--stub",
        ],
    )
    cli_start.main()
    assert captured["max_llm_calls"] == 30
