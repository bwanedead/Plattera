"""Tests for same-turn completion-anchor terminalization."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import pytest

from domains.mapping.deed_to_ir.semantics.closure import build_deed_to_ir_closure_policy
from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionRefusal,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
    SessionExecutionRecord,
)
from harness.execution.session import ExecutionSessionManager
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.action_sequence import ActionPlanAction
from harness.runtime.orchestration.action_sequence_hooks import run_action_sequence_turn_if_present
from harness.runtime.orchestration.completion_anchor_terminal import (
    evaluate_same_turn_completion_anchor,
    is_success_like_execution_state,
)
from harness.runtime.orchestration.contracts import ActionPlan
from harness.runtime.orchestration.test_completion_anchor import (
    _latest_refs,
    _publish_result_record,
)
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection, TerminalEvaluation
from harness.mission_state import new_mission_state, new_resolution_state
from tooling.mapping.deed_to_ir.publish_gate_feedback import build_final_output_summary

_PACK_CJ = {"pack_continuity_stub": True}

_PREVIEW_REF = "deed_to_ir:final_package_preview:rev:0001"
_MAPPING_B = "feature_graph:mapping:scope_b"
_FINALIZER = "finalize_current_deed_to_ir_output"


def _deed_closure_policy(*, terminal: bool = True) -> dict[str, Any]:
    policy = asdict(build_deed_to_ir_closure_policy())
    anchor = dict(policy["completion_anchor"])
    anchor["terminal_on_satisfied_anchor"] = terminal
    policy["completion_anchor"] = anchor
    return policy


def _publish_outputs() -> dict[str, Any]:
    return {
        "output_ref": "deed_to_ir:output",
        "output_revision_ref": "deed_to_ir:output:rev:0001",
        "mapping_artifact_ref": _MAPPING_B,
        "ir_artifact_ref": "feature_graph:ir:example_scope_v1",
        "final_package_preview_ref": _PREVIEW_REF,
        "finalization_status": "published",
        "final_output_summary": build_final_output_summary(publish_succeeded=True),
    }


def _action_plan(*, action_type: str = _FINALIZER, extra_action: bool = False) -> ActionPlan:
    actions = (ActionPlanAction("a1", action_type, {}),)
    if extra_action:
        actions = actions + (ActionPlanAction("a2", "hydrate_artifact_refs", {"ref_ids": ["x"]}),)
    return ActionPlan(
        actions=actions,
        idempotency_key="ik-finalize",
        continuity_journal_entry={"step": "finalize"},
    )


def _seed_loop_memory(*, include_publish_record: bool = True) -> LoopMemoryState:
    mem = LoopMemoryState()
    mem.continuity.latest_refs = _latest_refs()
    if include_publish_record:
        mem.continuity.kernel_step_result_records = [_publish_result_record()]
    return mem


def _evaluate(
    mem: LoopMemoryState,
    *,
    policy: dict[str, Any] | None = None,
    action_plan: ActionPlan | None = None,
    records: list[Any] | None = None,
):
    return evaluate_same_turn_completion_anchor(
        closure_policy=policy if policy is not None else _deed_closure_policy(terminal=True),
        action_plan=action_plan or _action_plan(),
        latest_refs=mem.continuity.latest_refs,
        step_result_records=(
            records
            if records is not None
            else mem.continuity.kernel_step_result_records
        ),
    )


def _historical_satisfied_record(**kwargs: Any) -> dict[str, Any]:
    return _publish_result_record(**kwargs)


def test_is_success_like_execution_state() -> None:
    assert is_success_like_execution_state(ExecutionState.EXECUTED)
    assert is_success_like_execution_state(ExecutionState.DEDUPED)
    assert not is_success_like_execution_state(ExecutionState.REFUSED)


def test_opted_in_sole_publish_satisfied_anchor_terminals() -> None:
    mem = _seed_loop_memory()
    decision = _evaluate(mem)
    assert decision is not None
    assert decision.terminal_class == "completed"
    assert decision.terminal_reason_code == "completion_anchor_satisfied"
    assert decision.completion_anchor["satisfied"] is True
    assert "expected_next" not in decision.completion_anchor


def test_default_off_policy_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    decision = _evaluate(mem, policy=_deed_closure_policy(terminal=False))
    assert decision is None


def test_unconfigured_action_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    decision = _evaluate(mem, action_plan=_action_plan(action_type="save_ir_artifact"))
    assert decision is None


def test_multi_action_plan_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    decision = _evaluate(mem, action_plan=_action_plan(extra_action=True))
    assert decision is None


def test_unsatisfied_anchor_does_not_terminal() -> None:
    mem = _seed_loop_memory(include_publish_record=False)
    decision = _evaluate(mem, records=[])
    assert decision is None


def test_ready_for_completion_false_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    record = dict(_publish_result_record())
    outputs = dict(record["outputs_for_continuity"])
    outputs["final_output_summary"] = {
        "ready_for_completion_candidate": False,
        "hydrate_output_ref_optional": False,
    }
    record["outputs_for_continuity"] = outputs
    mem.continuity.kernel_step_result_records = [record]
    decision = _evaluate(mem)
    assert decision is None


def test_missing_output_ref_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    refs = dict(_latest_refs())
    refs.pop("output", None)
    mem.continuity.latest_refs = refs
    decision = _evaluate(mem)
    assert decision is None


def test_missing_mapping_lineage_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    record = _publish_result_record(mapping_ref="feature_graph:mapping:missing")
    mem.continuity.kernel_step_result_records = [record]
    decision = _evaluate(mem)
    assert decision is None


def test_preview_lineage_mismatch_does_not_terminal() -> None:
    mem = _seed_loop_memory()
    mem.continuity.latest_refs = _latest_refs(preview_ref="deed_to_ir:final_package_preview:rev:0099")
    decision = _evaluate(mem)
    assert decision is None


@pytest.mark.parametrize("execution_state", ["executed", "deduped"])
def test_success_like_states_terminal_when_eligible(execution_state: str) -> None:
    mem = _seed_loop_memory(include_publish_record=False)
    record = dict(_publish_result_record())
    record["execution_state"] = execution_state
    mem.continuity.kernel_step_result_records = [record]
    decision = _evaluate(mem)
    assert decision is not None
    assert decision.terminal_reason_code == "completion_anchor_satisfied"


def test_refusal_does_not_terminal() -> None:
    mem = _seed_loop_memory(include_publish_record=False)
    decision = _evaluate(
        mem,
        records=[
            {
                "kernel_turn_index": 1,
                "action_type": _FINALIZER,
                "execution_state": "refused",
                "outputs_for_continuity": {},
                "artifact_refs": [],
            }
        ],
    )
    assert decision is None


def test_historical_satisfied_current_missing_readiness_does_not_terminal() -> None:
    current = dict(_publish_result_record(turn=2))
    outputs = dict(current["outputs_for_continuity"])
    outputs["final_output_summary"] = {
        "ready_for_completion_candidate": False,
        "hydrate_output_ref_optional": False,
    }
    current["outputs_for_continuity"] = outputs
    mem = _seed_loop_memory(include_publish_record=False)
    mem.continuity.kernel_step_result_records = [
        _historical_satisfied_record(turn=1),
        current,
    ]
    assert _evaluate(mem) is None


def test_historical_satisfied_current_missing_output_ref_does_not_terminal() -> None:
    current = dict(_publish_result_record(turn=2))
    outputs = dict(current["outputs_for_continuity"])
    outputs.pop("output_ref", None)
    outputs.pop("output_revision_ref", None)
    current["outputs_for_continuity"] = outputs
    mem = _seed_loop_memory(include_publish_record=False)
    mem.continuity.latest_refs = _latest_refs()
    mem.continuity.kernel_step_result_records = [
        _historical_satisfied_record(turn=1),
        current,
    ]
    assert _evaluate(mem) is None


def test_historical_satisfied_current_non_publish_action_does_not_terminal() -> None:
    mem = _seed_loop_memory(include_publish_record=False)
    mem.continuity.kernel_step_result_records = [
        _historical_satisfied_record(turn=1),
        {
            "kernel_turn_index": 2,
            "action_type": "hydrate_artifact_refs",
            "execution_state": "executed",
            "outputs_for_continuity": {"results": []},
            "artifact_refs": [],
        },
    ]
    assert _evaluate(mem) is None


def test_current_fully_satisfied_finalizer_still_terminalizes_with_history_present() -> None:
    mem = _seed_loop_memory(include_publish_record=False)
    mem.continuity.kernel_step_result_records = [
        _historical_satisfied_record(turn=1),
        _publish_result_record(turn=2),
    ]
    decision = _evaluate(mem)
    assert decision is not None
    assert decision.terminal_reason_code == "completion_anchor_satisfied"


class _FinalizePublishSessionManager(ExecutionSessionManager):
    def __init__(self, *, dedupe: bool = False) -> None:
        super().__init__()
        self.dedupe = dedupe
        self._calls = 0
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self._calls += 1
        self.steps.append(request)
        outputs = _publish_outputs()
        refs = {
            "output": "deed_to_ir:output",
            "preview": _PREVIEW_REF,
            "mapping": _MAPPING_B,
            "ir": "feature_graph:ir:example_scope_v1",
        }
        result = ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs=outputs,
            artifact_refs=tuple(refs.values()),
        )
        record = SessionExecutionRecord(
            session_id=request.session_id,
            run_id="r",
            request=request,
            result=result,
        )
        state = ExecutionState.DEDUPED if self.dedupe else ExecutionState.EXECUTED
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=state,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs=refs),
                budgets_remaining={},
                last_refusal=None,
            ),
            refusal=None,
            record=record,
        )


class _RefusalFinalizeSessionManager(ExecutionSessionManager):
    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        result = ActionDispatchResult(
            action_id=request.action_id,
            executed=False,
            refusal=ExecutionRefusal(
                reason_code="missing_finalization_decisions",
                retryable=True,
            ),
        )
        record = SessionExecutionRecord(
            session_id=request.session_id,
            run_id="r",
            request=request,
            result=result,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.REFUSED,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs={}),
                budgets_remaining={},
                last_refusal=result.refusal,
            ),
            refusal=result.refusal,
            record=record,
        )


class _StubTracer:
    def emit_execution_result(self, **kwargs: Any) -> None:
        return None

    def emit_state_patch_outcome(self, **kwargs: Any) -> None:
        return None


class _RecordingObserver:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def observe_turn_completed(self, record: dict[str, Any]) -> None:
        self.records.append(record)


def test_action_sequence_terminalizes_finalize_turn_with_state_patch_and_lifecycle() -> None:
    observer = _RecordingObserver()
    mem = LoopMemoryState()
    sm = _FinalizePublishSessionManager()
    tracer = _StubTracer()
    plan = ActionPlan(
        actions=(ActionPlanAction("a1", _FINALIZER, {}),),
        idempotency_key="ik-finalize",
        continuity_journal_entry={"step": "finalize published"},
        state_patch={"mission": {"work_universe_posture": "audited"}},
    )
    outcome = run_action_sequence_turn_if_present(
        loop_memory=mem,
        session_manager=sm,
        session_id="sess",
        action_plan=plan,
        iteration=1,
        request_id_prefix="req",
        run_id="run",
        run_ctx={"domain_closure_policy": _deed_closure_policy(terminal=True)},
        tracer=tracer,
        turn_completion_observer=observer,
        patch_present=True,
    )
    assert outcome.handled is True
    assert outcome.terminal_class == "completed"
    assert outcome.terminal_reason_code == "completion_anchor_satisfied"
    assert len(observer.records) == 1
    assert observer.records[0]["terminal_decision"] == "completion_anchor_satisfied"
    assert observer.records[0]["completion_anchor"]["satisfied"] is True
    assert mem.continuity.mission_state.work_universe_posture == "audited"
    assert mem.continuity.mission_state.closure_state.ready_to_close is False
    assert not mem.continuity.resolution_state.items
    assert not mem.continuity.mission_state.closure_state.dimensions
    assert mem.continuity.latest_refs["output"] == "deed_to_ir:output"
    assert mem.continuity.latest_refs["preview"] == _PREVIEW_REF
    assert mem.continuity.latest_refs["mapping"] == _MAPPING_B
    step = mem.continuity.kernel_step_result_records[-1]
    assert step["action_type"] == _FINALIZER
    assert step["execution_state"] == "executed"
    assert mem.continuity.continuity_journal_entries
    journal_payload = mem.continuity.continuity_journal_entries[-1]["author_payload"]
    assert journal_payload["author_addendum"] == {"step": "finalize published"}


def test_action_sequence_deduped_finalize_does_not_fall_through_refusal() -> None:
    observer = _RecordingObserver()
    mem = LoopMemoryState()
    sm = _FinalizePublishSessionManager(dedupe=True)
    tracer = _StubTracer()
    outcome = run_action_sequence_turn_if_present(
        loop_memory=mem,
        session_manager=sm,
        session_id="sess",
        action_plan=_action_plan(),
        iteration=1,
        request_id_prefix="req",
        run_id="run",
        run_ctx={"domain_closure_policy": _deed_closure_policy(terminal=True)},
        tracer=tracer,
        turn_completion_observer=observer,
        patch_present=False,
    )
    assert outcome.terminal_class == "completed"
    assert outcome.terminal_reason_code == "completion_anchor_satisfied"


def test_action_sequence_refusal_does_not_terminal() -> None:
    mem = LoopMemoryState()
    sm = _RefusalFinalizeSessionManager()
    tracer = _StubTracer()
    outcome = run_action_sequence_turn_if_present(
        loop_memory=mem,
        session_manager=sm,
        session_id="sess",
        action_plan=_action_plan(),
        iteration=1,
        request_id_prefix="req",
        run_id="run",
        run_ctx={"domain_closure_policy": _deed_closure_policy(terminal=True)},
        tracer=tracer,
        turn_completion_observer=None,
        patch_present=False,
    )
    assert outcome.terminal_class is None


class _ArtifactRefsDerivedFinalizeSessionManager(ExecutionSessionManager):
    """Production-shaped: latest_refs derived only from returned artifact_refs."""

    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        outputs = _publish_outputs()
        # Same shape as output_persistence._build_publish_success_result after BR-027.
        artifact_refs = (
            "deed_to_ir:output",
            "deed_to_ir:output:rev:0001",
            _MAPPING_B,
            "feature_graph:control:example",
            "feature_graph:clean:example",
            "feature_graph:geometry:example",
            "feature_graph:compile:example",
            "feature_graph:judge:example",
            "feature_graph:ir:example_scope_v1",
            _PREVIEW_REF,
        )
        assert artifact_refs.count(_PREVIEW_REF) == 1
        latest = {ref: ref for ref in artifact_refs}
        result = ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs=outputs,
            artifact_refs=artifact_refs,
        )
        record = SessionExecutionRecord(
            session_id=request.session_id,
            run_id="r",
            request=request,
            result=result,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs=latest),
                budgets_remaining={},
                last_refusal=None,
            ),
            refusal=None,
            record=record,
        )


class _MissingPreviewArtifactRefsFinalizeSessionManager(ExecutionSessionManager):
    """Outputs claim preview, but artifact_refs omit it (run-41 failure shape)."""

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        outputs = _publish_outputs()
        artifact_refs = (
            "deed_to_ir:output",
            "deed_to_ir:output:rev:0001",
            _MAPPING_B,
            "feature_graph:ir:example_scope_v1",
        )
        latest = {ref: ref for ref in artifact_refs}
        result = ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs=outputs,
            artifact_refs=artifact_refs,
        )
        record = SessionExecutionRecord(
            session_id=request.session_id,
            run_id="r",
            request=request,
            result=result,
        )
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=ExecutionDashboard(
                latest_refs=ExecutionLatestRefs(refs=latest),
                budgets_remaining={},
                last_refusal=None,
            ),
            refusal=None,
            record=record,
        )


def test_producer_artifact_refs_drive_same_turn_completion_anchor() -> None:
    """Preview must reach latest_refs via artifact_refs — not a hand-seeded preview key."""
    from harness.runtime.orchestration.completion_anchor import collect_ref_strings

    observer = _RecordingObserver()
    mem = LoopMemoryState()
    sm = _ArtifactRefsDerivedFinalizeSessionManager()
    tracer = _StubTracer()
    outcome = run_action_sequence_turn_if_present(
        loop_memory=mem,
        session_manager=sm,
        session_id="sess-producer",
        action_plan=_action_plan(),
        iteration=1,
        request_id_prefix="req",
        run_id="run",
        run_ctx={"domain_closure_policy": _deed_closure_policy(terminal=True)},
        tracer=tracer,
        turn_completion_observer=observer,
        patch_present=False,
    )
    assert outcome.handled is True
    assert outcome.terminal_class == "completed"
    assert outcome.terminal_reason_code == "completion_anchor_satisfied"
    assert observer.records[0]["completion_anchor"]["satisfied"] is True
    assert observer.records[0]["completion_anchor"]["preview_ref"] == _PREVIEW_REF
    # Derive from artifact_refs merge shape ({ref: ref}), not a semantic "preview" key.
    assert "preview" not in mem.continuity.latest_refs
    assert _PREVIEW_REF in mem.continuity.latest_refs
    assert _PREVIEW_REF in collect_ref_strings(mem.continuity.latest_refs)
    step = mem.continuity.kernel_step_result_records[-1]
    assert step["artifact_refs"].count(_PREVIEW_REF) == 1
    assert step["outputs_for_continuity"]["final_package_preview_ref"] == _PREVIEW_REF


def test_missing_preview_in_artifact_refs_does_not_terminalize() -> None:
    mem = LoopMemoryState()
    sm = _MissingPreviewArtifactRefsFinalizeSessionManager()
    tracer = _StubTracer()
    outcome = run_action_sequence_turn_if_present(
        loop_memory=mem,
        session_manager=sm,
        session_id="sess-missing-preview-refs",
        action_plan=_action_plan(),
        iteration=1,
        request_id_prefix="req",
        run_id="run",
        run_ctx={"domain_closure_policy": _deed_closure_policy(terminal=True)},
        tracer=tracer,
        turn_completion_observer=None,
        patch_present=False,
    )
    assert outcome.handled is True
    assert outcome.terminal_class is None
    assert _PREVIEW_REF not in mem.continuity.latest_refs


class _OneTurnFinalizePack:
    def __init__(self) -> None:
        self.choose_action_calls = 0

    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        return SharedStateProjection(
            mission_state=new_mission_state(mission_id="m-finalize", loop_family="orchestration_kernel"),
            resolution_state=new_resolution_state(),
        )

    def evaluate_terminal(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ) -> TerminalEvaluation | None:
        return None

    def choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
    ) -> ActionPlan:
        self.choose_action_calls += 1
        if self.choose_action_calls > 1:
            raise AssertionError("model caller invoked more than once")
        return ActionPlan(
            actions=(ActionPlanAction("f1", _FINALIZER, {}),),
            idempotency_key="ik-one-turn-finalize",
            continuity_journal_entry=_PACK_CJ,
        )


def test_orchestrator_completes_on_single_successful_finalize_turn() -> None:
    pack = _OneTurnFinalizePack()
    result = run_orchestration_kernel_loop(
        orchestration_adapter=pack,
        session_manager=_FinalizePublishSessionManager(),
        session_id="sess-one-turn",
        run_artifact_ref=None,
        request_id_prefix="req-one-turn",
        opaque_run_context={"domain_closure_policy": _deed_closure_policy(terminal=True)},
        max_iterations=5,
    )
    assert pack.choose_action_calls == 1
    assert result.terminal_class == "completed"
    assert result.reason_code == "completion_anchor_satisfied"
    assert result.iterations == 1


def test_action_sequence_without_terminal_opt_in_does_not_set_terminal_class() -> None:
    mem = LoopMemoryState()
    sm = _FinalizePublishSessionManager()
    tracer = _StubTracer()
    outcome = run_action_sequence_turn_if_present(
        loop_memory=mem,
        session_manager=sm,
        session_id="sess",
        action_plan=_action_plan(),
        iteration=1,
        request_id_prefix="req",
        run_id="run",
        run_ctx={"domain_closure_policy": _deed_closure_policy(terminal=False)},
        tracer=tracer,
        turn_completion_observer=None,
        patch_present=False,
    )
    assert outcome.handled is True
    assert outcome.terminal_class is None
