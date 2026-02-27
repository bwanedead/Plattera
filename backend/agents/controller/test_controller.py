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
    _autofill_known_args,
    _bound_run_summary_memory,
    _build_run_summary_entry,
    _build_context_packet,
    _build_fix_skeleton,
    _compute_controller_idempotency_key,
    _controller_proposal_log_payload,
    _ir_health_from_hint,
    _recommended_next_moves,
    _refusal_repair_request,
    _safe_artifact_hint,
    _semantic_span_repair_signature_for_context,
    _semantic_span_repair_thrash_refusal,
    run_controller_loop,
)
from backend.agents.controller.contracts import KernelStepProposal, kernel_step_tool_spec


class _FakeLLM:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self._responses = responses
        self.calls = 0

    def propose_next_step(
        self,
        *,
        model: str,
        tools: list[object],
        tool_choice_name: str,
        developer_message: str,
        user_message: str,
    ) -> dict[str, object]:
        del model, tools, tool_choice_name, developer_message, user_message
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
                "inputs": dict(request.inputs),
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


def test_non_string_notes_do_not_poison_valid_action_proposal() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "claimability should pass now",
                    "notes": {"unexpected": ["shape", 1]},
                    "declare_done": {
                        "artifact_refs": {"ir_ref": "artifacts/ir/ir-001.json"},
                        "evidence_links": [],
                        "accepted_deviations": [],
                    },
                }
            }
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
        max_iterations=1,
    )

    assert result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert not any(event["event_type"] == "controller_parse_failed" for event in transcript["events"])


def test_declare_done_missing_payload_autofills_and_executes() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "compile, judge, and bundle are present so try completion",
                }
            }
        ]
    )
    dashboard = _dashboard()
    dashboard.latest_refs = KernelLatestRefs(
        ir_ref={"artifact_path": "artifacts/feature_graphs/D1/ir.json"},
        compile_ref={"artifact_path": "artifacts/feature_graphs/D1/compile.json"},
        judge_ref={"artifact_path": "artifacts/feature_graphs/D1/judge.json"},
        bundle_ref={"artifact_path": "artifacts/feature_graphs/D1/bundle.json"},
    )
    dashboard.claimability = KernelClaimabilityStatus(claimable_ready=True, missing_claimability=[])
    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.SUCCESS,
        stop_reason=StopReason.COMPLETED,
        success=True,
        reason_code="declare_done_accepted",
    )
    step_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="ctl-any",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-001"},
        refusal=None,
        dashboard=dashboard,
        terminal=terminal,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.DECLARE_DONE.value],
            dashboard=dashboard,
            budgets_remaining=dashboard.budgets_remaining,
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
    assert len(manager.step_calls) == 1
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert not any(event["event_type"] == "controller_parse_failed" for event in transcript["events"])
    assert not any(
        event["event_type"] == "controller_refusal"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("refusal", {}).get("reason_code") == "declare_done_justification_missing"
        for event in transcript["events"]
    )


def test_controller_parse_failure_payload_includes_bounded_raw_diagnostics() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "error": "schema_validation_failed",
                "structured_data": {"foo": "bar", "nested": {"x": 1}},
                "text": '{"foo":"bar"}',
                "tool_calls_seen": ["draft_ir"],
            },
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
                }
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
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    parse_events = [e for e in transcript["events"] if e["event_type"] == "controller_parse_failed"]
    assert parse_events
    payload = parse_events[0]["payload"]
    assert payload["structured_data_keys"] == ["foo", "nested"]
    assert "structured_data_excerpt" in payload
    assert payload["tool_calls_seen"] == ["draft_ir"]


def test_parse_failure_triggers_one_step_controller_resync_open_artifact() -> None:
    llm = _FakeLLM(
        responses=[
            {"text": "{bad json", "error": "invalid_json"},
            {"text": "{still bad", "error": "invalid_json"},
        ]
    )
    dash = _dashboard()
    dash.latest_refs = KernelLatestRefs(judge_ref={"artifact_path": "artifacts/feature_graphs/judge_1.json"})
    step_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="k1",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-open"},
        refusal=None,
        dashboard=dash,
        terminal=None,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
            dashboard=dash,
            budgets_remaining=dash.budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=1,
    )

    assert manager.step_calls
    assert manager.step_calls[0]["action_type"] == ActionType.OPEN_ARTIFACT.value
    assert manager.step_calls[0]["inputs"]["artifact_ref"] == "artifacts/feature_graphs/judge_1.json"
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert any(event["event_type"] == "controller_parse_fail_resync" for event in transcript["events"])


def test_safe_artifact_hint_allows_feature_graph_judge_artifacts_and_surfaces_top_gaps() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original_legacy_dossiers_root = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            judge_path = _patched_root() / "artifacts" / "feature_graphs" / "D1" / "judge_1.json"
            judge_path.parent.mkdir(parents=True, exist_ok=True)
            judge_path.write_text(
                json.dumps(
                    {
                        "artifact_type": "judge",
                        "graph_id": "g1",
                        "report": {
                            "gaps": [
                                {
                                    "kind": "unsupported_operation",
                                    "operation_name": "Traverse",
                                    "feature_id": "curve_1",
                                    "message": "Operation not found",
                                }
                            ],
                            "warnings": ["w1"],
                        },
                    }
                ),
                encoding="utf-8",
            )
            hint = _safe_artifact_hint(str(judge_path), kind="judge")
            assert hint["status"] == "ok"
            assert isinstance(hint.get("top_gaps"), list) and hint["top_gaps"]
            assert hint["top_gaps"][0]["operation"] == "Traverse"
        finally:
            legacy_paths.dossiers_root = original_legacy_dossiers_root  # type: ignore[assignment]


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
        last_refusal_action_type_raw=None,
        last_step_result=None,
        run_summary_ref=None,
        run_summary_excerpt=None,
        phase_hint="verify",
        recent_digest_memory=[],
    )
    recent = packet.get("recent_trace")
    assert isinstance(recent, list)
    assert len(recent) <= 8
    assert isinstance(packet.get("tool_cheatsheet"), list)
    ir_ops_menu = packet.get("ir_ops_menu")
    assert isinstance(ir_ops_menu, dict)
    assert isinstance(ir_ops_menu.get("supported_compilable_ops"), list)
    assert "LineStep" in ir_ops_menu.get("supported_compilable_ops", [])
    assert isinstance(ir_ops_menu.get("authoring_rules"), list)


def test_kernel_step_tool_spec_includes_iteration_summary_property() -> None:
    spec = kernel_step_tool_spec()
    params = spec.parameters_schema
    props = params["properties"]
    assert "iteration_summary" in props


def test_context_packet_preserves_full_deed_text_and_fix_skeleton_uses_live_deed_ref() -> None:
    full_text = "LOT 1 " * 2000
    packet = _build_context_packet(
        session_id="s1",
        tool_menu=[ActionType.OPEN_ARTIFACT.value],
        bootstrap_context={
            "dossier_id": "D1",
            "deed_text_excerpt": "LOT 1",
            "deed_text_artifact_ref": "artifacts/deed/full.json",
            "deed_text_full": full_text,
        },
        dashboard=_dashboard().model_dump(mode="json"),
        transcript=[],
        last_refusal=None,
        last_refusal_action_type_raw=None,
        last_step_result=None,
        run_summary_ref=None,
        run_summary_excerpt=None,
        phase_hint="bootstrap",
        recent_digest_memory=[],
    )
    inputs = packet.get("inputs")
    assert isinstance(inputs, dict)
    assert inputs.get("deed_text_full") == full_text

    fix = _build_fix_skeleton(
        reason_code="open_artifact_requires_artifact_or_corpus_ref",
        action_type_raw=ActionType.OPEN_ARTIFACT.value,
        bootstrap_context={"deed_text_artifact_ref": "artifacts/deed/full.json"},
    )
    assert fix["kernel_step"]["args"]["artifact_ref"] == "artifacts/deed/full.json"


def test_context_packet_memory_includes_span_index_ref_and_catalog_excerpt() -> None:
    packet = _build_context_packet(
        session_id="s1",
        tool_menu=[ActionType.OPEN_TEXT_SPANS.value, ActionType.UPSERT_DEED_SPAN_INDEX.value],
        bootstrap_context={"dossier_id": "D1", "deed_text_artifact_ref": "artifacts/deed/d1.json"},
        dashboard=_dashboard().model_dump(mode="json"),
        transcript=[],
        last_refusal=None,
        last_refusal_action_type_raw=None,
        last_step_result=None,
        run_summary_ref=None,
        run_summary_excerpt=None,
        phase_hint="bootstrap",
        recent_digest_memory=[
            {
                "iter": 2,
                "digest_ref": "artifacts/digests/i2.json",
                "digest_excerpt": "iter=2",
                "deed_span_index_ref": "artifacts/spans/index.json",
                "deed_span_catalog_excerpt": [{"span_id": "calls_01", "kind": "metes_bounds_calls"}],
                "run_summary_entry": {
                    "iter": 2,
                    "source": "fallback",
                    "action": "propose:open_text_spans; observed_last:executed",
                    "actual_observation": "executed",
                    "expected_observation": "next iteration should observe updated refs/gaps after open_text_spans",
                },
            }
        ],
    )
    memory = packet.get("memory")
    assert isinstance(memory, dict)
    assert memory.get("deed_span_index_ref") == "artifacts/spans/index.json"
    assert isinstance(memory.get("deed_span_catalog_excerpt"), list)
    run_summary_log = memory.get("run_summary_log")
    assert isinstance(run_summary_log, list)
    assert run_summary_log
    assert isinstance(run_summary_log[0], dict)
    assert "actual_observation" in run_summary_log[0]
    cheatsheet = packet.get("tool_cheatsheet")
    assert isinstance(cheatsheet, list)
    actions = {entry.get("action_type") for entry in cheatsheet if isinstance(entry, dict)}
    assert ActionType.OPEN_TEXT_SPANS.value in actions
    assert ActionType.UPSERT_DEED_SPAN_INDEX.value in actions
    open_text_entry = next(entry for entry in cheatsheet if isinstance(entry, dict) and entry.get("action_type") == ActionType.OPEN_TEXT_SPANS.value)
    assert isinstance(open_text_entry.get("iteration_summary_note"), str)


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


def test_context_packet_last_refusal_includes_rejected_graph_repair_refs() -> None:
    refusal = KernelRefusal(
        reason_code="draft_ir_graph_validation_failed",
        missing_inputs=[],
        retryable=True,
        blocked_by_budget=False,
        blocked_by_invariant=False,
    )
    step_result = KernelStepResult(
        session_id="s1",
        idempotency_key="k1",
        execution_state=StepExecutionState.REFUSED,
        step_record={
            "step_id": "step-001",
            "outputs_inline": {
                "kernel_refusal": refusal.model_dump(mode="json"),
                "rejected_graph_artifact_ref": {"artifact_path": "artifacts/rejected/r1.json"},
                "rejected_graph_summary": {"status": "invalid", "node_count": 1},
            },
        },
        refusal=refusal,
        dashboard=_dashboard(),
        terminal=None,
    )
    packet = _build_context_packet(
        session_id="s1",
        tool_menu=[ActionType.DRAFT_IR.value],
        bootstrap_context={"dossier_id": "D1"},
        dashboard=_dashboard().model_dump(mode="json"),
        transcript=[],
        last_refusal=refusal,
        last_refusal_action_type_raw=ActionType.DRAFT_IR.value,
        last_step_result=step_result,
        run_summary_ref=None,
        run_summary_excerpt=None,
        phase_hint="author_ir",
        recent_digest_memory=[],
    )
    last_refusal_payload = packet.get("last_refusal")
    assert isinstance(last_refusal_payload, dict)
    assert last_refusal_payload["reason_code"] == "draft_ir_graph_validation_failed"
    assert last_refusal_payload["rejected_graph_artifact_ref"]["artifact_path"] == "artifacts/rejected/r1.json"
    assert isinstance(last_refusal_payload["rejected_graph_summary"], dict)
    assert "how_to" in last_refusal_payload


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
                        "graph": {
                            "graph_id": "g_draft_001",
                            "nodes": [
                                {"id": "n1", "kind": "point", "geometry": {"type": "Point", "coordinates": [0, 0]}}
                            ],
                            "edges": [],
                            "metadata": {"source": "deed"},
                        },
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
    assert isinstance(manager.step_calls[0]["inputs"].get("graph"), dict)


def test_open_artifact_empty_args_are_autofilled_from_deed_ref() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "open deed artifact",
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
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result],
    )
    start_request = _start_request().model_copy(
        update={
            "initial_ir_ref": None,
            "dossier_id": "D1",
            "source_entry_ref": "final:D1",
            "initial_graph_json": {
                "graph_id": "g1",
                "nodes": [],
                "edges": [],
                "metadata": {
                    "deed_text_artifact_ref": "artifacts/deed/d1.json",
                    "deed_text_excerpt": "excerpt",
                },
            },
        }
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=start_request,
        max_iterations=2,
    )
    assert result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    assert manager.step_calls
    assert manager.step_calls[0]["inputs"]["artifact_ref"] == "artifacts/deed/d1.json"


def test_open_artifact_empty_args_prefers_judge_then_compile_then_ir_before_deed() -> None:
    filled, fields = _autofill_known_args(
        action_type=ActionType.OPEN_ARTIFACT,
        args={},
        bootstrap_context={"deed_text_artifact_ref": "artifacts/deed/d1.json"},
        dashboard={
            "latest_refs": {
                "judge_ref": {"artifact_path": "artifacts/judge/j1.json"},
                "compile_ref": {"artifact_path": "artifacts/compile/c1.json"},
                "ir_ref": {"artifact_path": "artifacts/ir/i1.json"},
            }
        },
        context_packet={"memory": {}},
    )
    assert "artifact_ref" in fields
    assert filled["artifact_ref"] == "artifacts/judge/j1.json"


def test_repeated_open_artifact_same_ref_triggers_inspection_thrash_brake() -> None:
    llm = _FakeLLM(
        responses=[
            {"structured_data": {"action_type": "open_artifact", "idempotency_key": "k1", "args": {"artifact_ref": "artifacts/judge/j1.json"}, "why": "inspect"}},
            {"structured_data": {"action_type": "open_artifact", "idempotency_key": "k2", "args": {"artifact_ref": "artifacts/judge/j1.json"}, "why": "inspect again"}},
            {"structured_data": {"action_type": "open_artifact", "idempotency_key": "k3", "args": {"artifact_ref": "artifacts/judge/j1.json"}, "why": "inspect again"}},
        ]
    )
    dash = _dashboard()
    dash.latest_refs = KernelLatestRefs(
        ir_ref={"artifact_path": "artifacts/ir/ir-001.json"},
        judge_ref={"artifact_path": "artifacts/judge/j1.json"},
    )
    step_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="k-open",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-open"},
        refusal=None,
        dashboard=dash,
        terminal=None,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
            dashboard=dash,
            budgets_remaining=dash.budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result, step_result, step_result],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=3,
    )

    assert len(manager.step_calls) == 1
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert any(
        e.get("event_type") == "controller_refusal"
        and isinstance(e.get("payload"), dict)
        and isinstance(e.get("payload", {}).get("refusal"), dict)
        and e.get("payload", {}).get("refusal", {}).get("reason_code") == "repeated_inspection_no_progress"
        for e in transcript["events"]
    )


def test_repeated_open_text_spans_same_args_triggers_span_thrash_brake() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_text_spans",
                    "idempotency_key": "k1",
                    "args": {
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                        "anchors": [{"start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"}],
                    },
                    "why": "read tie language",
                }
            },
            {
                "structured_data": {
                    "action_type": "open_text_spans",
                    "idempotency_key": "k2",
                    "args": {
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                        "anchors": [{"start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"}],
                    },
                    "why": "read again",
                }
            },
            {
                "structured_data": {
                    "action_type": "open_text_spans",
                    "idempotency_key": "k3",
                    "args": {
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                        "anchors": [{"start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"}],
                    },
                    "why": "read again",
                }
            },
        ]
    )
    dash = _dashboard()
    dash.latest_refs = KernelLatestRefs(
        ir_ref={"artifact_path": "artifacts/ir/ir-001.json"},
        judge_ref={"artifact_path": "artifacts/judge/j1.json"},
    )
    step_result = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="k-open-spans",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-open-spans"},
        refusal=None,
        dashboard=dash,
        terminal=None,
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.OPEN_TEXT_SPANS.value],
            dashboard=dash,
            budgets_remaining=dash.budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result, step_result, step_result],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=3,
    )

    assert len(manager.step_calls) == 1
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert any(
        e.get("event_type") == "controller_refusal"
        and isinstance(e.get("payload"), dict)
        and isinstance(e.get("payload", {}).get("refusal"), dict)
        and e.get("payload", {}).get("refusal", {}).get("reason_code") == "repeated_span_open_no_progress"
        for e in transcript["events"]
    )


def test_semantic_span_repair_signature_detects_centroid_tie_loop_context() -> None:
    sig = _semantic_span_repair_signature_for_context(
        {
            "progress": {
                "latest_refs": {
                    "ir_ref": "artifacts/ir/i1.json",
                    "validate_ref": "artifacts/validate/v1.json",
                    "deed_span_index_ref": None,
                },
                "map_sanity_excerpt": {
                    "validate_top_issues": [
                        "agent_kernel_section_centroid_anchor_fallback",
                        "agent_kernel_unresolved_tie_to_corner_reference",
                    ]
                },
            }
        }
    )
    assert isinstance(sig, str)
    assert "section_centroid_anchor_fallback" in sig
    assert "unresolved_tie_to_corner" in sig


def test_semantic_span_repair_thrash_refusal_triggers_after_repeated_reads() -> None:
    context_packet = {
        "progress": {
            "latest_refs": {
                "ir_ref": "artifacts/ir/i1.json",
                "validate_ref": "artifacts/validate/v1.json",
            },
            "map_sanity_excerpt": {
                "validate_top_issues": [
                    "agent_kernel_section_centroid_anchor_fallback",
                    "agent_kernel_unresolved_tie_to_corner_reference",
                ]
            },
        }
    }
    sig = _semantic_span_repair_signature_for_context(context_packet)
    assert isinstance(sig, str)
    refusal = _semantic_span_repair_thrash_refusal(
        action_type=ActionType.OPEN_TEXT_SPANS,
        context_packet=context_packet,
        repeated_signature=sig,
        repeated_count=2,
    )
    assert refusal is not None
    assert refusal[0].reason_code == "semantic_repair_span_loop_no_progress"


def test_refusal_repair_request_overrides_semantic_span_loop_to_draft_ir() -> None:
    req = _refusal_repair_request(
        action_type_raw=ActionType.OPEN_TEXT_SPANS.value,
        refusal=KernelRefusal(reason_code="semantic_repair_span_loop_no_progress", retryable=True),
        bootstrap_context={"dossier_id": "D1", "deed_text_artifact_ref": "artifacts/deed/d1.json"},
        context_inputs={
            "dossier_id": "D1",
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "deed_span_index_ref": None,
        },
    )
    assert isinstance(req, dict)
    assert req.get("action_type") == ActionType.DRAFT_IR.value
    example = req.get("minimal_working_example")
    assert isinstance(example, dict)
    assert isinstance(example.get("graph"), dict)


def test_redundant_compile_is_refused_before_kernel_step() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "compile",
                    "idempotency_key": "k1",
                    "args": {"ir_artifact_ref": "artifacts/ir/ir-001.json"},
                    "why": "compile again",
                }
            }
        ]
    )
    dash = _dashboard()
    dash.latest_refs = KernelLatestRefs(
        ir_ref={"artifact_path": "artifacts/ir/ir-001.json"},
        compile_ref={"artifact_path": "artifacts/compile/c-001.json"},
    )
    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.FAILED,
        stop_reason=StopReason.BUDGET_EXCEEDED,
        success=False,
        reason_code="controller_iterations_exhausted_or_parse_failed",
    )
    manager = _FakeSessionManager(
        start_result=KernelSessionStartResult(
            session_id="controller-req-001::run-001",
            run_id="run-001",
            run_artifact_ref="in-memory://run-001",
            tool_menu=[ActionType.COMPILE.value],
            dashboard=dash,
            budgets_remaining=dash.budgets_remaining,
            refusal=None,
        ),
        step_results=[
            KernelStepResult(
                session_id="controller-req-001::run-001",
                idempotency_key="unused",
                execution_state=StepExecutionState.EXECUTED,
                step_record={"step_id": "step-001"},
                refusal=None,
                dashboard=dash,
                terminal=terminal,
            )
        ],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=1,
    )

    assert len(manager.step_calls) == 0
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    assert any(
        e.get("event_type") == "controller_refusal"
        and isinstance(e.get("payload"), dict)
        and e.get("payload", {}).get("refusal", {}).get("reason_code") == "compile_already_current"
        for e in transcript["events"]
    )


def test_open_text_spans_autofill_supplies_deed_ref_and_span_index_ref() -> None:
    filled, fields = _autofill_known_args(
        action_type=ActionType.OPEN_TEXT_SPANS,
        args={"span_ids": ["calls_01"]},
        bootstrap_context={"deed_text_artifact_ref": "artifacts/deed/d1.json"},
        dashboard={
            "latest_refs": {
                "deed_span_index_ref": {"artifact_path": "artifacts/spans/index.json"},
            }
        },
        context_packet={"memory": {"deed_span_index_ref": "artifacts/spans/index.json"}},
    )
    assert "deed_text_artifact_ref" in fields
    assert "deed_span_index_ref" in fields
    assert filled["deed_text_artifact_ref"] == "artifacts/deed/d1.json"
    assert filled["deed_span_index_ref"] == "artifacts/spans/index.json"


def test_recommended_next_prefers_ir_update_when_global_placement_missing_and_no_structured_anchor() -> None:
    progress = {
        "latest_refs": {
            "ir_ref": "artifacts/ir/ir-001.json",
            "compile_ref": "artifacts/compile/c-001.json",
            "judge_ref": "artifacts/judge/j-001.json",
            "bundle_ref": "artifacts/bundle/b-001.json",
        },
        "gap_summary": {"gap_counts_by_kind": {}},
        "claimability": {
            "claimable_ready": False,
            "missing_claimability": ["has_georef", "validation_passed"],
        },
        "ir_health": {"is_stub": False, "has_structured_plss_anchor": False},
    }

    recs = _recommended_next_moves(progress)

    joined = " | ".join(recs).lower()
    assert "plss_anchor" in joined
    assert "re-bundle" in joined
    assert "georeference" in joined
    assert "open_artifact" not in joined


def test_recommended_next_prefers_draft_ir_before_compile_when_ir_is_stub() -> None:
    progress = {
        "latest_refs": {"ir_ref": "artifacts/ir/ir-stub.json"},
        "ir_health": {"is_stub": True, "has_structured_plss_anchor": False, "has_local_polygon_geometry": False},
    }

    recs = _recommended_next_moves(progress)

    assert recs
    assert recs[0].lower().startswith("draft_ir")


def test_recommended_next_prefers_polygon_repair_when_georef_missing_and_anchor_present() -> None:
    progress = {
        "latest_refs": {
            "ir_ref": "artifacts/ir/ir-001.json",
            "compile_ref": "artifacts/compile/c-001.json",
            "judge_ref": "artifacts/judge/j-001.json",
            "bundle_ref": "artifacts/bundle/b-001.json",
        },
        "gap_summary": {"gap_counts_by_kind": {}},
        "claimability": {"claimable_ready": False, "missing_claimability": ["has_georef", "validation_passed"]},
        "ir_health": {"is_stub": False, "has_structured_plss_anchor": True, "has_local_polygon_geometry": False},
    }

    recs = _recommended_next_moves(progress)

    joined = " | ".join(recs).lower()
    assert "polygon" in joined
    assert "re-bundle" in joined
    assert "georeference" in joined


def test_recommended_next_prefers_tie_repair_on_centroid_fallback_issue() -> None:
    progress = {
        "latest_refs": {"georef_ref": "artifacts/georef/g-001.json", "validate_ref": "artifacts/validate/v-001.json"},
        "map_sanity_excerpt": {
            "validate_top_issues": ["agent_kernel_section_centroid_anchor_fallback"],
        },
    }
    recs = _recommended_next_moves(progress)
    joined = " | ".join(recs).lower()
    assert "tie_to_corner" in joined or "tie" in joined
    assert "centroid fallback" in joined


def test_build_fix_skeleton_georef_missing_plss_anchor_uses_canonical_plss_anchor_example() -> None:
    fix = _build_fix_skeleton(
        reason_code="georef_missing_plss_anchor",
        action_type_raw=ActionType.DRAFT_IR.value,
        bootstrap_context={"dossier_id": "D1", "deed_text_artifact_ref": "artifacts/deed/d1.json"},
    )
    graph = (((fix.get("kernel_step") or {}).get("args") or {}).get("graph") if isinstance((fix.get("kernel_step") or {}).get("args"), dict) else None)
    assert isinstance(graph, dict)
    graph_meta = graph.get("metadata")
    assert isinstance(graph_meta, dict)
    assert "plss_anchor" in graph_meta
    assert "plss" not in graph_meta or isinstance(graph_meta.get("plss_anchor"), dict)
    note = str(graph_meta.get("authoring_note") or "").lower()
    assert "plss_anchor" in note and "not plss" in note


def test_safe_artifact_hint_ir_requires_full_plss_anchor_fields() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            fg_dir = _patched_root() / "artifacts" / "feature_graphs" / "D_TEST"
            fg_dir.mkdir(parents=True, exist_ok=True)

            incomplete = fg_dir / "ir_incomplete.json"
            incomplete.write_text(
                json.dumps(
                    {
                        "artifact_type": "ir",
                        "graph": {
                            "graph_id": "g1",
                            "nodes": [
                                {
                                    "id": "frame1",
                                    "kind": "frame",
                                    "metadata": {"plss_anchor": {"state": "Wyoming", "township_number": 14}},
                                }
                            ],
                            "edges": [],
                            "metadata": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            complete = fg_dir / "ir_complete.json"
            complete.write_text(
                json.dumps(
                    {
                        "artifact_type": "ir",
                        "graph": {
                            "graph_id": "g2",
                            "nodes": [
                                {
                                    "id": "frame1",
                                    "kind": "frame",
                                    "metadata": {
                                        "plss_anchor": {
                                            "state": "Wyoming",
                                            "township_number": 14,
                                            "township_direction": "N",
                                            "range_number": 75,
                                            "range_direction": "W",
                                            "section_number": 2,
                                        }
                                    },
                                }
                            ],
                            "edges": [],
                            "metadata": {},
                        },
                    }
                ),
                encoding="utf-8",
            )

            incomplete_hint = _safe_artifact_hint(str(incomplete), kind="ir")
            complete_hint = _safe_artifact_hint(str(complete), kind="ir")
            assert incomplete_hint.get("has_structured_plss_anchor") is False
            assert complete_hint.get("has_structured_plss_anchor") is True

            health = _ir_health_from_hint(complete_hint, str(complete))
            assert health["has_structured_plss_anchor"] is True
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_safe_artifact_hint_ir_detects_local_polygon_geometry() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            fg_dir = _patched_root() / "artifacts" / "feature_graphs" / "D_TEST"
            fg_dir.mkdir(parents=True, exist_ok=True)
            ir_file = fg_dir / "ir_polygon.json"
            ir_file.write_text(
                json.dumps(
                    {
                        "artifact_type": "ir",
                        "graph": {
                            "graph_id": "g-poly",
                            "nodes": [
                                {
                                    "id": "parcel1",
                                    "kind": "region",
                                    "geometry": {
                                        "type": "Polygon",
                                        "coordinates": [[[0, 0], [10, 0], [10, 5], [0, 0]]],
                                    },
                                }
                            ],
                            "edges": [],
                            "metadata": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            hint = _safe_artifact_hint(str(ir_file), kind="ir")
            assert hint.get("has_local_polygon_geometry") is True
            health = _ir_health_from_hint(hint, str(ir_file))
            assert health["has_local_polygon_geometry"] is True
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_safe_artifact_hint_ir_includes_parcel_audit() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            fg_dir = _patched_root() / "artifacts" / "feature_graphs" / "D_TEST"
            fg_dir.mkdir(parents=True, exist_ok=True)
            ir_file = fg_dir / "ir_parcel_audit.json"
            ir_file.write_text(
                json.dumps(
                    {
                        "artifact_type": "ir",
                        "graph": {
                            "graph_id": "g-audit",
                            "nodes": [
                                {"id": "parcel1", "kind": "region", "metadata": {}},
                                {
                                    "id": "parcel2_stub",
                                    "kind": "annotation",
                                    "metadata": {"note": "Parcel 2 stub; incomplete/truncated"},
                                },
                            ],
                            "edges": [],
                            "metadata": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            hint = _safe_artifact_hint(str(ir_file), kind="ir")
            parcel_audit = hint.get("parcel_audit")
            assert isinstance(parcel_audit, dict)
            assert parcel_audit.get("complete_region_count") == 1
            assert parcel_audit.get("partial_annotation_stub_count") == 1
            health = _ir_health_from_hint(hint, str(ir_file))
            assert isinstance(health.get("parcel_audit"), dict)
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]


def test_upsert_deed_span_index_autofill_supplies_deed_fingerprint() -> None:
    filled, fields = _autofill_known_args(
        action_type=ActionType.UPSERT_DEED_SPAN_INDEX,
        args={
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "upserts": [
                {
                    "span_id": "calls_01",
                    "kind": "metes_bounds_calls",
                    "labels": ["calls"],
                    "status": "proposed",
                    "start_char": 0,
                    "end_char": 20,
                }
            ],
        },
        bootstrap_context={
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "deed_fingerprint": {"sha256_12": "1234567890ab", "length_chars": 999},
        },
        dashboard={"latest_refs": {}},
        context_packet={"memory": {}},
    )
    assert "deed_fingerprint" in fields
    assert filled["deed_fingerprint"]["sha256_12"] == "1234567890ab"


def test_run_summary_log_bounding_drops_oldest_by_byte_budget() -> None:
    entries = []
    for i in range(80):
        entries.append(
            {
                "iter": i + 1,
                "run_summary_entry": {
                    "iter": i + 1,
                    "source": "agent",
                    "action": "open_artifact",
                    "intent": "x" * 500,
                    "actual_observation": "y" * 500,
                },
            }
        )
    bounded = _bound_run_summary_memory(entries)
    assert len(bounded) < len(entries)
    first_iter = bounded[0]["run_summary_entry"]["iter"]
    assert first_iter > 1


def test_fallback_run_summary_entry_generated_when_iteration_summary_missing() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "open deed",
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
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
            dashboard=_dashboard(),
            budgets_remaining=_dashboard().budgets_remaining,
            refusal=None,
        ),
        step_results=[step_result],
    )
    start_request = _start_request().model_copy(
        update={
            "initial_ir_ref": None,
            "dossier_id": "D1",
            "source_entry_ref": "final:D1",
            "initial_graph_json": {
                "graph_id": "g1",
                "nodes": [],
                "edges": [],
                "metadata": {
                    "deed_text_artifact_ref": "artifacts/deed/d1.json",
                    "deed_text_excerpt": "excerpt",
                },
            },
        }
    )
    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=start_request,
        max_iterations=2,
    )
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    header = next(e for e in transcript["events"] if e["event_type"] == "run_header")
    memory = header["payload"]["bootstrap_context"]  # sanity anchor only
    assert isinstance(memory, dict)
    kernel_event = next(e for e in transcript["events"] if e["event_type"] == "kernel_step_result")
    assert kernel_event["payload"]["execution_state"] == "executed"


def test_fallback_run_summary_entry_is_memory_docket_shaped() -> None:
    proposal = KernelStepProposal(
        action_type="retrieve_evidence",
        args={"query": "survey bearings"},
        idempotency_key="k1",
        why="check terminology before drafting",
    )
    entry = _build_run_summary_entry(
        iteration=3,
        phase_hint="retrieve",
        proposal=proposal,
        outcome_kind="controller_refusal",
        outcome_payload={
            "reason_code": "retrieve_evidence_requires_query",
            "missing_inputs": ["query"],
            "latest_refs": {},
        },
    )
    assert entry["source"] == "fallback"
    assert entry["iter"] == 3
    assert isinstance(entry.get("action"), str)
    assert isinstance(entry.get("actual_observation"), str)
    assert isinstance(entry.get("expected_observation"), str)
    assert isinstance(entry.get("next_move"), dict)
    assert isinstance(entry.get("open_issues"), list)


def test_agent_iteration_summary_is_normalized_to_memory_docket_shape() -> None:
    proposal = KernelStepProposal(
        action_type="open_artifact",
        args={"artifact_ref": "artifacts/deed/d1.json"},
        idempotency_key="k1",
        why="inspect deed summary",
        iteration_summary={
            "action": "propose:open_artifact; observed_last:refused(open_artifact_requires_artifact_or_corpus_ref)",
            "actual_observation": "refused(open_artifact_requires_artifact_or_corpus_ref)",
            "expected_observation": "next iteration should observe summary output for the deed artifact",
            "open_issues": ["missing artifact_ref in prior attempt", {"bad": "shape"}],
            "next_move": {"action_type": "open_artifact", "why": "use deed ref from inputs"},
            "extra_noise": "should be dropped",
        },
    )
    entry = _build_run_summary_entry(
        iteration=1,
        phase_hint="bootstrap",
        proposal=proposal,
        outcome_kind="executed",
        outcome_payload={"latest_refs": {}},
    )
    assert entry["source"] == "agent"
    assert entry["iter"] == 1
    assert "actual_observation" in entry
    assert "expected_observation" in entry
    assert "next_move" in entry
    assert "extra_noise" not in entry


def test_agent_iteration_summary_open_issues_string_is_coerced_to_list() -> None:
    proposal = KernelStepProposal(
        action_type="open_text_spans",
        args={
            "deed_text_artifact_ref": "artifacts/deed/d1.json",
            "spans": [{"start_char": 0, "end_char": 10}],
        },
        idempotency_key="k1",
        why="open a small deed span",
        iteration_summary={
            "actual_observation": "refused(open_text_spans_missing_deed_ref)",
            "open_issues": "need deed_text_artifact_ref",
            "next_move": {"action_type": "open_text_spans", "why": "use deed ref from inputs"},
        },
    )
    entry = _build_run_summary_entry(
        iteration=2,
        phase_hint="verify_source",
        proposal=proposal,
        outcome_kind="executed",
        outcome_payload={"latest_refs": {}},
    )
    issues = entry.get("open_issues")
    assert isinstance(issues, list)
    assert issues == ["need deed_text_artifact_ref"]


def test_controller_proposal_log_payload_includes_iteration_summary_excerpt() -> None:
    payload = _controller_proposal_log_payload(
        iteration=2,
        action_type="open_text_spans",
        args={"deed_text_artifact_ref": "artifacts/deed/d1.json", "anchors": [{"start_anchor": "BEGINNING AT", "end_anchor": "POINT OF BEGINNING"}]},
        why="open deed calls",
        iteration_summary={
            "actual_observation": "refused(open_text_spans_requires_span_ids_or_spans_or_anchors)",
            "expected_observation": "next iteration should observe span text after anchor request succeeds",
        },
    )
    assert isinstance(payload.get("iteration_summary_excerpt"), str)


def test_retryable_controller_refusal_triggers_repair_prompt_and_avoids_repeating_empty_draft_ir() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "draft_ir",
                    "idempotency_key": "k1",
                    "args": {},
                    "why": "draft",
                }
            },
            {
                "structured_data": {
                    "action_type": "draft_ir",
                    "idempotency_key": "k2",
                    "args": {
                        "dossier_id": "D1",
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                        "graph": {
                            "graph_id": "g_fix",
                            "nodes": [{"id": "n1", "kind": "point", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
                            "edges": [],
                            "metadata": {"source": "deed"},
                        },
                    },
                    "why": "repair using graph",
                }
            },
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
        max_iterations=4,
    )
    assert result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    assert manager.step_calls
    assert manager.step_calls[0]["action_type"] == ActionType.DRAFT_IR.value
    assert "graph" in manager.step_calls[0]["inputs"]


def test_iteration_summary_does_not_affect_step_inputs_or_idempotency() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "draft_ir",
                    "idempotency_key": "k1",
                    "args": {
                        "dossier_id": "D1",
                        "deed_text_artifact_ref": "artifacts/deed/d1.json",
                        "graph": {
                            "graph_id": "g1",
                            "nodes": [{"id": "n1", "kind": "point", "geometry": {"type": "Point", "coordinates": [0, 0]}}],
                            "edges": [],
                            "metadata": {"source": "deed"},
                        },
                    },
                    "why": "draft",
                    "iteration_summary": {
                        "action": "draft_ir",
                        "intent": "Trying first draft",
                        "actual_observation": "waiting on kernel",
                        "open_issues": ["need compile after draft"],
                    },
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
    assert manager.step_calls[0]["inputs"]["dossier_id"] == "D1"
    assert manager.step_calls[0]["inputs"]["deed_text_artifact_ref"] == "artifacts/deed/d1.json"
    assert isinstance(manager.step_calls[0]["inputs"]["graph"], dict)
    assert manager.step_calls[0]["idempotency_key"].startswith("ctl-")


def test_malformed_iteration_summary_does_not_block_valid_action_execution() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "artifacts/deed/d1.json"},
                    "why": "open deed",
                    "iteration_summary": ["weird", {"nested": "object"}, 123],
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
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
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
    assert manager.step_calls[0]["inputs"] == {"artifact_ref": "artifacts/deed/d1.json"}
    assert manager.step_calls[0]["idempotency_key"].startswith("ctl-")


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


def test_display_delta_missing_does_not_change_execution() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "artifacts/deed/d1.json"},
                    "why": "inspect deed summary",
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
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
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
    assert manager.step_calls[0]["inputs"] == {"artifact_ref": "artifacts/deed/d1.json"}
    assert manager.step_calls[0]["idempotency_key"].startswith("ctl-")


def test_malformed_display_delta_does_not_break_parse_and_is_stringified_in_transcript() -> None:
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "artifacts/deed/d1.json"},
                    "why": "inspect deed summary",
                    "display_delta": {"kind": "judge_update", "items": ["gap", 1]},
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
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
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

    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    proposed = next(e for e in transcript["events"] if e["event_type"] == "agent_proposed_step")
    assert not any(e["event_type"] == "controller_parse_failed" for e in transcript["events"])
    assert isinstance(proposed["payload"].get("display_delta"), str)


def test_display_delta_long_value_is_truncated() -> None:
    long_delta = "I am reviewing the deed calls and rebuilding the parcel draft after a new gap surfaced. " * 6
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "artifacts/deed/d1.json"},
                    "why": "inspect deed summary",
                    "display_delta": long_delta,
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
            tool_menu=[ActionType.OPEN_ARTIFACT.value],
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
    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    proposed = next(e for e in transcript["events"] if e["event_type"] == "agent_proposed_step")
    display_delta = proposed["payload"].get("display_delta")
    assert isinstance(display_delta, str)
    assert len(display_delta) <= 220


def test_repeated_identical_display_delta_is_deduped() -> None:
    same_delta = "I am checking the latest graph gaps before revising the parcel draft."
    llm = _FakeLLM(
        responses=[
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k1",
                    "args": {"artifact_ref": "artifacts/judge/j1.json"},
                    "why": "inspect judge",
                    "display_delta": same_delta,
                }
            },
            {
                "structured_data": {
                    "action_type": "open_artifact",
                    "idempotency_key": "k2",
                    "args": {"artifact_ref": "artifacts/judge/j2.json"},
                    "why": "inspect judge again",
                    "display_delta": same_delta,
                }
            },
        ]
    )
    step_result_1 = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="ctl-1",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-001"},
        refusal=None,
        dashboard=_dashboard(),
        terminal=None,
    )
    terminal = TerminalOutcome(
        terminal_outcome=TerminalOutcomeKind.SUCCESS,
        stop_reason=StopReason.COMPLETED,
        success=True,
        reason_code="done",
    )
    step_result_2 = KernelStepResult(
        session_id="controller-req-001::run-001",
        idempotency_key="ctl-2",
        execution_state=StepExecutionState.EXECUTED,
        step_record={"step_id": "step-002"},
        refusal=None,
        dashboard=_dashboard(),
        terminal=terminal,
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
        step_results=[step_result_1, step_result_2],
    )

    result = run_controller_loop(
        session_manager=manager,  # type: ignore[arg-type]
        llm_client=llm,  # type: ignore[arg-type]
        start_request=_start_request(),
        max_iterations=3,
    )

    transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
    proposed_events = [e for e in transcript["events"] if e["event_type"] == "agent_proposed_step"]
    assert len(proposed_events) >= 2
    assert proposed_events[0]["payload"].get("display_delta") == same_delta
    assert proposed_events[1]["payload"].get("display_delta") in (None, "")
