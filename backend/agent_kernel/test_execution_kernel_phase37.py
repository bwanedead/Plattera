"""Phase 37: execution/provider contract stays generic and coherent."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps, RegisteredProviderAction
from backend.agent_kernel.harness_action_ids import ActionType
from backend.agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest, KernelStepRequest, StepExecutionState
from backend.agent_kernel.ref_coercion import extract_output_ref, put_artifact_ref
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact
from backend.agent_kernel.session import KernelSessionManager
from backend.feature_graph.kernel_claimability import FeatureGraphClaimabilityPolicy


class _InMemorySessionPersistence:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], RunArtifact] = {}

    def save_run_artifact(self, run_artifact: RunArtifact) -> dict[str, object]:
        key = (run_artifact.request_id, run_artifact.run_id)
        self._store[key] = RunArtifact.model_validate(run_artifact.model_dump(mode="json"))
        return {"path": f"in-memory://{run_artifact.request_id}/{run_artifact.run_id}.json"}

    def get_run_artifact(self, request_id: str, run_id: str) -> RunArtifact | None:
        return self._store.get((request_id, run_id))


def test_provider_action_projector_and_terminal_hook_are_dispatched_through_session_step() -> None:
    projector_calls: list[tuple[str, str, str]] = []
    terminal_calls: list[str] = []

    def _compile_handler(_inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "artifact_ref": {"artifact_path": "artifacts/provider/compile-001.json"},
            "reason_codes": ["provider_compile_completed"],
        }

    def _judge_handler(_inputs: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "artifact_ref": {"artifact_path": "artifacts/provider/judge-001.json"},
            "reason_codes": ["provider_judge_completed"],
        }

    def _project_compile(run_artifact: RunArtifact, step) -> None:
        projector_calls.append((run_artifact.run_id, step.step_id, step.action))
        ref = extract_output_ref(step.outputs, "compile_artifact_ref")
        run_artifact.compile_artifact_ref = ref
        put_artifact_ref(run_artifact, "compile_artifact_ref", ref)

    def _project_judge(run_artifact: RunArtifact, step) -> None:
        projector_calls.append((run_artifact.run_id, step.step_id, step.action))
        ref = extract_output_ref(step.outputs, "judge_artifact_ref")
        run_artifact.judge_artifact_ref = ref
        put_artifact_ref(run_artifact, "judge_artifact_ref", ref)

    def _terminal_hook(run_artifact: RunArtifact) -> None:
        terminal_calls.append(run_artifact.run_id)
        run_artifact.artifact_refs["terminal_marker_ref"] = ArtifactRef(
            artifact_path="artifacts/provider/terminal-marker.json"
        )

    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            provider_actions={
                "fake_provider__compile": RegisteredProviderAction(
                    output_key="compile_artifact_ref",
                    reason_code="provider_compile_completed",
                    missing_reason="missing_provider_compile_handler",
                    handler=_compile_handler,
                ),
                "fake_provider__judge": RegisteredProviderAction(
                    output_key="judge_artifact_ref",
                    reason_code="provider_judge_completed",
                    missing_reason="missing_provider_judge_handler",
                    handler=_judge_handler,
                ),
            },
            provider_step_projectors={
                "fake_provider__compile": _project_compile,
                "fake_provider__judge": _project_judge,
            },
            terminal_success_hooks=(_terminal_hook,),
        )
    )
    persistence = _InMemorySessionPersistence()
    manager = KernelSessionManager(
        action_executor=executor,
        claimability_policy=FeatureGraphClaimabilityPolicy(),
        persistence_service=persistence,
    )
    started = manager.start_session(
        KernelSessionStartRequest(
            request_id="req-provider-001",
            goal=KernelGoal(
                requires_global_placement=False,
                render_required=False,
                objective="provider seam",
            ),
            budgets=KernelBudgets(
                max_steps=5,
                max_wall_time_seconds=60,
                max_retrieval_calls=1,
                max_semantic_calls=1,
                max_patch_calls=1,
            ),
            initial_ir_ref="artifacts/bootstrap/ir.json",
        )
    )

    assert started.refusal is None
    assert started.session_id is not None

    compile_result = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-compile",
            action_type="fake_provider__compile",
            inputs={},
        )
    )
    judge_result = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-judge",
            action_type="fake_provider__judge",
            inputs={},
        )
    )
    done_result = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-done",
            action_type=ActionType.DECLARE_DONE.value,
            inputs={},
        )
    )

    request_id, run_id = started.session_id.rsplit("::", maxsplit=1)
    stored = persistence.get_run_artifact(request_id=request_id, run_id=run_id)
    assert stored is not None

    assert compile_result.execution_state == StepExecutionState.EXECUTED
    assert judge_result.execution_state == StepExecutionState.EXECUTED
    assert done_result.execution_state == StepExecutionState.EXECUTED
    assert stored.compile_artifact_ref is not None
    assert stored.compile_artifact_ref.artifact_path == "artifacts/provider/compile-001.json"
    assert stored.judge_artifact_ref is not None
    assert stored.judge_artifact_ref.artifact_path == "artifacts/provider/judge-001.json"
    assert stored.artifact_refs["compile_artifact_ref"].artifact_path == "artifacts/provider/compile-001.json"
    assert stored.artifact_refs["judge_artifact_ref"].artifact_path == "artifacts/provider/judge-001.json"
    assert stored.artifact_refs["terminal_marker_ref"].artifact_path == "artifacts/provider/terminal-marker.json"
    assert projector_calls == [
        (run_id, "step-001", "fake_provider__compile"),
        (run_id, "step-002", "fake_provider__judge"),
    ]
    assert terminal_calls == [run_id]
