"""Tests for deterministic kernel loop core entrypoint."""

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
    EvidenceRetriever,
    Georeferencer,
    Judge,
    PatchProposer,
    Validator,
)
from backend.agent_kernel.kernel import IRGraphLoader, KernelLoopOutput, run_kernel
from backend.agent_kernel.models import (
    ActionType,
    KernelBudgets,
    KernelGoal,
    KernelRequest,
    StopReason,
    TerminalOutcomeKind,
)
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, StepRecord, ValidationInline


class _DeterministicServices(
    EvidenceRetriever,
    Compiler,
    Judge,
    Bundler,
    Georeferencer,
    Validator,
    PatchProposer,
):
    def __init__(self, validation_sequence: list[bool]) -> None:
        self._validation_sequence = validation_sequence
        self._validation_idx = 0

    def retrieve_evidence(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/retrieval/retrieval-001.json")

    def compile(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/compile/compile-001.json")

    def judge(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/judge/judge-001.json")

    def bundle(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/bundle/bundle-001.json")

    def georeference(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/georef/georef-001.json")

    def validate(self, inputs: Mapping[str, Any]) -> ValidationInline:
        del inputs
        passed = self._validation_sequence[min(self._validation_idx, len(self._validation_sequence) - 1)]
        self._validation_idx += 1
        return ValidationInline(
            passed=passed,
            reason_code="validation_failure" if not passed else "ok",
            checks={"error_count": 0 if passed else 1},
        )

    def propose_patch(self, inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        del inputs
        return {"patch": "retry-with-same-inputs"}


class _InMemoryPersistence:
    def __init__(self) -> None:
        self.saved: list[RunArtifact] = []

    def save_run_artifact(self, run_artifact: RunArtifact) -> dict[str, object]:
        self.saved.append(run_artifact)
        return {"path": f"in-memory://{run_artifact.request_id}/{run_artifact.run_id}.json"}


class _StaticIRGraphLoader(IRGraphLoader):
    def load_graph(self, ir_artifact_ref: ArtifactRef) -> dict[str, object]:
        del ir_artifact_ref
        return {"metadata": {}, "nodes": [{"id": "n1"}]}


class _WorkerUnavailableRetrievalExecutor(ActionExecutor):
    def execute(self, step_id: str, action: Any, inputs: Mapping[str, Any]) -> StepRecord:
        if action == ActionType.RETRIEVE_EVIDENCE:
            return StepRecord(
                step_id=step_id,
                action=action,
                inputs=dict(inputs),
                reason_codes=["semantic_worker_in_backoff"],
            )
        return super().execute(step_id=step_id, action=action, inputs=inputs)


def _request(
    *,
    requires_global_placement: bool,
    max_steps: int = 20,
    initial_ir_ref: str | None = "artifacts/ir/ir-initial.json",
    initial_graph_json: dict[str, object] | None = None,
) -> KernelRequest:
    return KernelRequest(
        request_id="req-kernel-loop",
        goal=KernelGoal(
            requires_global_placement=requires_global_placement,
            objective="deterministic kernel loop test",
        ),
        budgets=KernelBudgets(
            max_steps=max_steps,
            max_wall_time_seconds=60,
            max_retrieval_calls=10,
            max_semantic_calls=10,
            max_patch_calls=10,
        ),
        initial_ir_ref=initial_ir_ref,
        initial_graph_json=initial_graph_json,
    )


def _executor(validation_sequence: list[bool]) -> ActionExecutor:
    services = _DeterministicServices(validation_sequence=validation_sequence)
    deps = ActionExecutorDeps(
        evidence_retriever=services,
        compiler=services,
        judge=services,
        bundler=services,
        georeferencer=services,
        validator=services,
        patch_proposer=services,
    )
    return ActionExecutor(deps=deps)


def test_run_kernel_emits_kernel_result_and_run_artifact() -> None:
    persistence = _InMemoryPersistence()
    output = run_kernel(
        _request(requires_global_placement=False),
        action_executor=_executor([True]),
        persistence_service=persistence,
    )

    assert isinstance(output, KernelLoopOutput)
    assert output.kernel_result.request_id == "req-kernel-loop"
    assert output.kernel_result.terminal.stop_reason == StopReason.COMPLETED
    assert output.kernel_result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
    assert output.kernel_result.steps_executed == len(output.run_artifact.steps)
    assert output.run_artifact.request_id == "req-kernel-loop"
    assert len(persistence.saved) == 1


def test_requires_global_placement_runs_set_graph_requirements_before_compile_and_judge() -> None:
    output = run_kernel(
        _request(requires_global_placement=True),
        action_executor=_executor([True]),
        ir_graph_loader=_StaticIRGraphLoader(),
    )
    actions = [step.action.value for step in output.run_artifact.steps]

    assert actions[0] == "set_graph_requirements"
    assert "compile" in actions
    assert "judge" in actions
    assert actions.index("set_graph_requirements") < actions.index("compile")
    assert actions.index("set_graph_requirements") < actions.index("judge")


def test_budget_exceeded_sets_deterministic_stop_reason() -> None:
    output = run_kernel(
        _request(requires_global_placement=True, max_steps=1),
        action_executor=_executor([True]),
        ir_graph_loader=_StaticIRGraphLoader(),
    )

    assert output.kernel_result.terminal.stop_reason == StopReason.BUDGET_EXCEEDED
    assert output.kernel_result.terminal.reason_code == "budget_steps_exceeded"


def test_repeated_validation_failures_classify_as_validation_failed() -> None:
    output = run_kernel(
        _request(requires_global_placement=False, max_steps=30),
        action_executor=_executor([False, False, False]),
        no_progress_max_stagnant_repair_cycles=1,
    )

    assert output.kernel_result.terminal.stop_reason == StopReason.VALIDATION_FAILED
    assert output.kernel_result.terminal.reason_code == "validation_failure"
    assert output.kernel_result.terminal.terminal_outcome == TerminalOutcomeKind.PARTIAL


def test_missing_initial_ir_ref_is_classified_as_needs_upload() -> None:
    output = run_kernel(
        _request(requires_global_placement=False, initial_ir_ref=None),
        action_executor=_executor([True]),
    )

    assert output.kernel_result.terminal.stop_reason == StopReason.NEEDS_UPLOAD
    assert output.kernel_result.terminal.reason_code == "missing_initial_ir_ref_or_graph_json"
    assert output.kernel_result.terminal.terminal_outcome == TerminalOutcomeKind.NEEDS_UPLOAD


def test_initial_graph_json_without_ir_ref_does_not_require_upload() -> None:
    output = run_kernel(
        _request(
            requires_global_placement=False,
            initial_ir_ref=None,
            initial_graph_json={"metadata": {"inline": True}, "nodes": [{"id": "n-inline"}]},
        ),
        action_executor=_executor([True]),
    )

    assert output.kernel_result.terminal.stop_reason == StopReason.COMPLETED
    assert output.kernel_result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS


def test_semantic_worker_in_backoff_maps_to_worker_unavailable_stop_reason() -> None:
    services = _DeterministicServices(validation_sequence=[True])
    deps = ActionExecutorDeps(
        evidence_retriever=services,
        compiler=services,
        judge=services,
        bundler=services,
        georeferencer=services,
        validator=services,
        patch_proposer=services,
    )
    output = run_kernel(
        _request(requires_global_placement=True),
        action_executor=_WorkerUnavailableRetrievalExecutor(deps=deps),
        ir_graph_loader=_StaticIRGraphLoader(),
    )

    assert output.kernel_result.terminal.stop_reason == StopReason.WORKER_UNAVAILABLE
    assert output.kernel_result.terminal.reason_code == "semantic_worker_in_backoff"
    assert output.kernel_result.terminal.terminal_outcome == TerminalOutcomeKind.FAILED
