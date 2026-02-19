"""Tests for step-driven kernel session manager contracts and behavior."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import (
    ActionExecutor,
    ActionExecutorDeps,
    Bundler,
    Compiler,
    Judge,
    Validator,
)
from backend.agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    KernelStepRequest,
    StepExecutionState,
    StopReason,
)
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, ValidationInline
from backend.agent_kernel.session import KernelSessionManager


class _DeterministicServices(Compiler, Judge, Bundler, Validator):
    def compile(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/compile/compile-001.json")

    def judge(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/judge/judge-001.json")

    def bundle(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/bundle/bundle-001.json")

    def validate(self, inputs: Mapping[str, Any]) -> ValidationInline:
        del inputs
        return ValidationInline(passed=True, reason_code="ok", checks={})


class _InMemorySessionPersistence:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], RunArtifact] = {}

    def save_run_artifact(self, run_artifact: RunArtifact) -> dict[str, object]:
        key = (run_artifact.request_id, run_artifact.run_id)
        self._store[key] = RunArtifact.model_validate(run_artifact.model_dump(mode="json"))
        return {"path": f"in-memory://{run_artifact.request_id}/{run_artifact.run_id}.json"}

    def get_run_artifact(self, request_id: str, run_id: str) -> RunArtifact | None:
        return self._store.get((request_id, run_id))


def _start_request() -> KernelSessionStartRequest:
    return KernelSessionStartRequest(
        request_id="req-session-001",
        goal=KernelGoal(requires_global_placement=False, objective="session test"),
        budgets=KernelBudgets(
            max_steps=5,
            max_wall_time_seconds=60,
            max_retrieval_calls=3,
            max_semantic_calls=3,
            max_patch_calls=3,
        ),
        initial_ir_ref="artifacts/ir/ir-001.json",
    )


def _session_manager() -> tuple[KernelSessionManager, _InMemorySessionPersistence]:
    services = _DeterministicServices()
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            compiler=services,
            judge=services,
            bundler=services,
            validator=services,
        )
    )
    persistence = _InMemorySessionPersistence()
    return (
        KernelSessionManager(
            action_executor=executor,
            persistence_service=persistence,
        ),
        persistence,
    )


def test_start_session_initializes_without_running_tools() -> None:
    manager, persistence = _session_manager()
    result = manager.start_session(_start_request())

    assert result.refusal is None
    assert result.session_id is not None
    request_id, run_id = result.session_id.rsplit("::", maxsplit=1)
    stored = persistence.get_run_artifact(request_id=request_id, run_id=run_id)
    assert stored is not None
    assert stored.steps == []
    assert len(result.tool_menu) > 0
    assert ActionType.COMPILE.value in result.tool_menu
    assert ActionType.DECLARE_DONE.value in result.tool_menu
    assert result.dashboard is not None


def test_start_session_refuses_when_bootstrap_inputs_missing() -> None:
    manager, _ = _session_manager()
    request = _start_request().model_copy(update={"initial_ir_ref": None})
    result = manager.start_session(request)

    assert result.refusal is not None
    assert result.refusal.reason_code == "bootstrap_missing_inputs"
    assert result.dashboard is not None
    assert result.tool_menu == []


def test_start_session_persists_initial_graph_json_as_ir_artifact_ref() -> None:
    manager, persistence = _session_manager()
    request = _start_request().model_copy(
        update={
            "initial_ir_ref": None,
            "initial_graph_json": {"metadata": {"source": "inline"}, "nodes": [{"id": "n1"}]},
        }
    )
    result = manager.start_session(request)

    assert result.refusal is None
    assert result.session_id is not None
    request_id, run_id = result.session_id.rsplit("::", maxsplit=1)
    stored = persistence.get_run_artifact(request_id=request_id, run_id=run_id)
    assert stored is not None
    assert stored.ir_artifact_ref is not None
    assert run_id in stored.ir_artifact_ref.artifact_path


def test_start_session_tool_menu_is_capability_aware_for_default_manager() -> None:
    persistence = _InMemorySessionPersistence()
    manager = KernelSessionManager(persistence_service=persistence)
    result = manager.start_session(_start_request())

    assert result.refusal is None
    assert ActionType.HYDRATE_DEED.value in result.tool_menu
    assert ActionType.OPEN_ARTIFACT.value in result.tool_menu
    assert ActionType.DRAFT_IR.value in result.tool_menu
    assert ActionType.RETRIEVE_EVIDENCE.value in result.tool_menu
    assert ActionType.COMPILE.value in result.tool_menu
    assert ActionType.JUDGE.value in result.tool_menu
    assert ActionType.DECLARE_DONE.value in result.tool_menu


def test_start_session_refuses_oversized_initial_graph_json() -> None:
    manager, _ = _session_manager()
    oversized = {"nodes": [{"id": "n", "payload": "x" * 300000}]}
    request = _start_request().model_copy(
        update={
            "initial_ir_ref": None,
            "initial_graph_json": oversized,
        }
    )
    result = manager.start_session(request)

    assert result.refusal is not None
    assert result.refusal.reason_code == "bootstrap_graph_payload_too_large"
    assert result.refusal.blocked_by_invariant is True


def test_step_executes_exactly_one_action_and_persists_step() -> None:
    manager, persistence = _session_manager()
    started = manager.start_session(_start_request())
    assert started.session_id is not None

    step = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-001",
            action_type=ActionType.COMPILE,
            inputs={},
            semantic_ready=True,
        )
    )
    assert step.execution_state == StepExecutionState.EXECUTED
    assert step.refusal is None
    assert step.step_record is not None
    assert step.dashboard.semantic_ready is True

    request_id, run_id = started.session_id.rsplit("::", maxsplit=1)
    stored = persistence.get_run_artifact(request_id=request_id, run_id=run_id)
    assert stored is not None
    assert len(stored.steps) == 1
    assert stored.steps[0].action == ActionType.COMPILE


def test_step_idempotency_dedupes_and_payload_mismatch_refuses() -> None:
    manager, _ = _session_manager()
    started = manager.start_session(_start_request())
    assert started.session_id is not None

    first = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-dup",
            action_type=ActionType.COMPILE,
            inputs={},
        )
    )
    deduped = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-dup",
            action_type=ActionType.COMPILE,
            inputs={},
        )
    )
    mismatched = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-dup",
            action_type=ActionType.COMPILE,
            inputs={"different": "payload"},
        )
    )

    assert first.execution_state == StepExecutionState.EXECUTED
    assert deduped.execution_state == StepExecutionState.DEDUPED
    assert mismatched.execution_state == StepExecutionState.REFUSED
    assert mismatched.refusal is not None
    assert mismatched.refusal.reason_code == "idempotency_key_payload_mismatch"


def test_declare_done_refuses_until_claimability_is_satisfied_then_succeeds() -> None:
    manager, _ = _session_manager()
    started = manager.start_session(_start_request())
    assert started.session_id is not None

    refused = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-done-0",
            action_type=ActionType.DECLARE_DONE,
            inputs={},
        )
    )
    assert refused.execution_state == StepExecutionState.REFUSED
    assert refused.refusal is not None
    assert refused.refusal.reason_code == "declare_done_claimability_missing"

    manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-done-1",
            action_type=ActionType.COMPILE,
            inputs={},
        )
    )
    manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-done-2",
            action_type=ActionType.JUDGE,
            inputs={},
        )
    )
    accepted = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-done-3",
            action_type=ActionType.DECLARE_DONE,
            inputs={},
        )
    )
    assert accepted.execution_state == StepExecutionState.EXECUTED
    assert accepted.terminal is not None
    assert accepted.terminal.stop_reason == StopReason.COMPLETED
