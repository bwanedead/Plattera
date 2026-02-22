from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config.paths as legacy_paths
from backend.agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelClaimabilityStatus,
    KernelDashboard,
    KernelFailureClassification,
    KernelGapSummary,
    KernelGoal,
    KernelLatestRefs,
    KernelNoProgressRisk,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelStepResult,
    StepExecutionState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from backend.agents.controller.controller import (
    _append_event,
    _build_context_packet,
    _compute_controller_idempotency_key,
    _safe_artifact_hint,
    run_controller_loop,
)


class _FakeLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = responses
        self.calls = 0

    def propose_next_step(
        self,
        *,
        model: str,
        schema: dict[str, object],
        prompt: str,
    ) -> dict[str, object]:
        del model, schema, prompt
        idx = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[idx]


class _FakeSessionManager:
    def __init__(
        self,
        *,
        start_result: KernelSessionStartResult,
        step_results: list[KernelStepResult],
    ) -> None:
        self._start_result = start_result
        self._step_results = step_results
        self.step_calls: list[dict[str, object]] = []

    def start_session(self, request: KernelSessionStartRequest) -> KernelSessionStartResult:
        del request
        return self._start_result

    def step(self, request: Any) -> KernelStepResult:
        self.step_calls.append(
            {
                "action_type": request.action_type.value,
                "semantic_ready": request.semantic_ready,
                "idempotency_key": request.idempotency_key,
            }
        )
        idx = min(len(self.step_calls) - 1, len(self._step_results) - 1)
        return self._step_results[idx]


def _dashboard() -> KernelDashboard:
    return KernelDashboard(
        latest_refs=KernelLatestRefs(),
        gap_summary=KernelGapSummary(),
        claimability=KernelClaimabilityStatus(claimable_ready=False, missing_claimability=["has_ir"]),
        semantic_ready=None,
        budgets_remaining={
            "steps_remaining": 5,
            "wall_time_seconds_remaining": 60,
            "retrieval_calls_remaining": 5,
            "semantic_calls_remaining": 5,
            "patch_calls_remaining": 5,
        },
        failure_classification=KernelFailureClassification(stop_reason=None, reason_code=None),
        no_progress_risk=KernelNoProgressRisk(risk_score=0.0, basis="not_computed_v0"),
        last_refusal=None,
    )


def _start_request() -> KernelSessionStartRequest:
    return KernelSessionStartRequest(
        request_id="controller-req-001",
        goal=KernelGoal(requires_global_placement=False, objective="controller test"),
        budgets=KernelBudgets(
            max_steps=10,
            max_wall_time_seconds=120,
            max_retrieval_calls=10,
            max_semantic_calls=10,
            max_patch_calls=10,
        ),
        initial_ir_ref="artifacts/ir/ir-001.json",
    )


def test_controller_retries_once_on_json_parse_failure_and_then_executes() -> None:
    llm = _FakeLLM(
        responses=[
            {"text": "{bad json", "error": "invalid_json"},
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "claimability should pass now",
                    "declare_done": {
                        "artifact_refs": {"ir_ref": "artifacts/ir/ir-001.json"},
                        "evidence_links": [],
                        "accepted_deviations": [],
                    },
                },
            },
        ]
    )
    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.SUCCESS,
        stop_reason=StopReason.COMPLETED,
        success=True,
        reason_code="declare_done_accepted",
    )
    step_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="k1",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-001"},
        refusal=None,
        dashboard=_dashboard(),
        terminal=terminal,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.DECLARE_DONE.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=2,
    )

    assert result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    assert llm.calls == 2
    assert manager.step_calls[0]["idempotency_key"].startswith("ctl-")
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert any(event["event_type"] == "controller_parse_failed" for event in transcript["events"])


def test_controller_passes_kernel_refusal_through_to_transcript() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "try declare done",
                    "declare_done": {
                        "artifact_refs": {"ir_ref": "artifacts/ir/ir-001.json"},
                        "evidence_links": [],
                        "accepted_deviations": [],
                    },
                },
            },
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k2",
                    "args": {},
                    "why": "retry declare done",
                    "declare_done": {
                        "artifact_refs": {"ir_ref": "artifacts/ir/ir-001.json"},
                        "evidence_links": [],
                        "accepted_deviations": [],
                    },
                },
            },
        ]
    )
    refusal = KernelRefusal(
        reason_code="declare_done_claimability_missing",
        missing_inputs=["has_judge"],
        retryable=True,
        blocked_by_budget=False,
        blocked_by_invariant=False,
    )
    refused_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="k1",
        execution_state=StepExecutionState.REFUSED,
        step_record={"step_id": "step-001"},
        refusal=refusal,
        dashboard=_dashboard(),
        terminal=None,
    )
    success_terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.SUCCESS,
        stop_reason=StopReason.COMPLETED,
        success=True,
        reason_code="declare_done_accepted",
    )
    executed_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="k2",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-002"},
        refusal=None,
        dashboard=_dashboard(),
        terminal=success_terminal,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.DECLARE_DONE.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[refused_result, executed_result],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=3,
    )

    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    refusal_payloads = [
        event["payload"]["refusal"]
        for event in transcript["events"]
        if event["event_type"] == "kernel_step_result" and event["payload"].get("refusal") is not None
    ]
    assert refusal_payloads[0]["reason_code"] == "declare_done_claimability_missing"
    assert refusal_payloads[0]["missing_inputs"] == ["has_judge"]
    assert refusal_payloads[0]["retryable"] is True
    assert refusal_payloads[0]["blocked_by_budget"] is False
    assert refusal_payloads[0]["blocked_by_invariant"] is False


def test_controller_rejects_action_not_in_tool_menu_and_semantic_ready_is_audit_only() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "compile",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "not allowed in this menu",
                    "semantic_ready": True,
                }
            }
        ]
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.DECLARE_DONE.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=1,
    )

    assert result.terminal.terminal_outcome == TerminalOutcomeKind.FAILED
    assert len(manager.step_calls) == 0


def test_append_event_enforces_event_caps_and_truncation_markers() -> None:
    events: list[dict[str, object]] = []
    for idx in range(230):
        _append_event(
            events,
            event_type="x" * 80,
            detail="d" * 4000,
            payload={"i": idx},
        )

    assert len(events) <= 200
    assert events[0]["event_type"] == "transcript_truncated"
    assert str(events[-1]["detail"]).endswith("...[truncated]")


def test_controller_refuses_retrieve_evidence_missing_query_before_kernel_call() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "retrieve_evidence",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "retrieve without query",
                }
            }
        ]
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.RETRIEVE_EVIDENCE.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=1,
    )

    assert result.terminal.terminal_outcome == TerminalOutcomeKind.FAILED
    assert len(manager.step_calls) == 0
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    refusal_events = [e for e in transcript["events"] if e["event_type"] == "controller_refusal"]
    assert refusal_events
    assert refusal_events[0]["detail"] == "retrieve_evidence_inputs_invalid"
    assert "fix" in refusal_events[0]["payload"]
    assert "required_fields" in refusal_events[0]["payload"]["fix"]


def test_controller_refuses_too_deep_args_before_kernel_call() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "a", "junk": {"a": {"b": {"c": {"d": {"e": {"f": {"g": {"h": {"i": 1}}}}}}}}}},
                    "why": "too deep",
                }
            }
        ]
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=1,
    )

    assert result.terminal.terminal_outcome == TerminalOutcomeKind.FAILED
    assert len(manager.step_calls) == 0
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    refusal_events = [e for e in transcript["events"] if e["event_type"] == "controller_refusal"]
    assert refusal_events
    assert refusal_events[0]["detail"] == "controller_inputs_depth_exceeded"


def test_controller_computes_deterministic_idempotency_key() -> None:
    key1 = _compute_controller_idempotency_key(
        session_id="s1",
        iteration=2,
        action_type="compile",
        inputs={"ir_artifact_ref": "a"},
    )
    key2 = _compute_controller_idempotency_key(
        session_id="s1",
        iteration=2,
        action_type="compile",
        inputs={"ir_artifact_ref": "a"},
    )
    key3 = _compute_controller_idempotency_key(
        session_id="s1",
        iteration=3,
        action_type="compile",
        inputs={"ir_artifact_ref": "a"},
    )
    assert key1 == key2
    assert key1 != key3
    assert key1.startswith("ctl-")


def test_context_packet_trace_is_bounded() -> None:
    events: list[dict[str, object]] = []
    for idx in range(40):
        _append_event(
            events,
            event_type="kernel_step_result",
            detail="executed",
            payload={"iteration": idx, "action_type": "compile"},
        )
    packet = _build_context_packet(
        session_id="s1",
        tool_menu=[ActionType.COMPILE.value],
        bootstrap_context={"dossier_id": "D1", "deed_text_excerpt": "x" * 3000},
        dashboard=_dashboard().model_dump(mode="json"),
        transcript=events,
        last_refusal=None,
        run_summary_ref=None,
        run_summary_excerpt=None,
        phase_hint="verify",
    )
    recent = packet.get("recent_trace")
    assert isinstance(recent, list)
    assert len(recent) <= 8


def test_no_progress_brake_triggers_on_repeated_same_refusal() -> None:
    llm = _FakeLLM(
        responses=[
            {"structured_data": {"action_type": "retrieve_evidence", "idempotency_key": "k1", "args": {}, "why": "x"}},
            {"structured_data": {"action_type": "retrieve_evidence", "idempotency_key": "k2", "args": {}, "why": "x"}},
            {"structured_data": {"action_type": "retrieve_evidence", "idempotency_key": "k3", "args": {}, "why": "x"}},
        ]
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.RETRIEVE_EVIDENCE.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[],
    )
    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=10,
    )
    assert result.terminal.stop_reason == StopReason.NO_PROGRESS
    assert result.terminal.reason_code.startswith("controller_no_progress:")


def test_no_progress_brake_does_not_trigger_for_retrieve_with_changed_queries() -> None:
    llm = _FakeLLM(
        responses=[
            {"structured_data": {"action_type": "retrieve_evidence", "idempotency_key": "k1", "args": {"query": "alpha"}, "why": "x"}},
            {"structured_data": {"action_type": "retrieve_evidence", "idempotency_key": "k2", "args": {"query": "beta"}, "why": "x"}},
            {"structured_data": {"action_type": "retrieve_evidence", "idempotency_key": "k3", "args": {"query": "gamma"}, "why": "x"}},
        ]
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[],
    )
    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=3,
    )
    assert result.terminal.stop_reason != StopReason.NO_PROGRESS
    assert result.terminal.reason_code == "controller_iterations_exhausted_or_parse_failed"


def test_draft_ir_with_deed_text_artifact_ref_reaches_kernel_step() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "draft_ir",
                    "idempotency_key": "k1",
                    "args": {
                        "dossier_id": "D1",
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                    },
                    "why": "draft from bootstrapped deed ref",
                }
            }
        ]
    )
    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.SUCCESS,
        stop_reason=StopReason.COMPLETED,
        success=True,
        reason_code="done",
    )
    step_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="ctl-any",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-001"},
        refusal=None,
        dashboard=_dashboard(),
        terminal=terminal,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.DRAFT_IR.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result],
    )
    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=2,
    )
    assert result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    assert manager.step_calls
    assert manager.step_calls[0]["action_type"] == ActionType.DRAFT_IR.value


def test_safe_artifact_hint_blocks_out_of_root_and_large_file() -> None:
    blocked = _safe_artifact_hint("C:\\Windows\\System32\\drivers\\etc\\hosts", kind="deed")
    assert blocked["status"] == "blocked_path"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            target = _patched_root() / "artifacts" / "agent_kernel" / "too_big.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x" * 70000, encoding="utf-8")
            hint = _safe_artifact_hint(str(target), kind="ir")
            assert hint["status"] == "too_large"
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]
