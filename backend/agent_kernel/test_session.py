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
    DraftIRProposer,
    Judge,
    Renderer,
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
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, StepRecord, ValidationInline
from backend.agent_kernel.session import KernelSessionManager
from backend.agent_kernel import session as kernel_session_module


class _DeterministicServices(Compiler, Judge, Bundler, Validator, Renderer):
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

    def render(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/render/render-001.json")


class _RefusingDraftIR(DraftIRProposer):
    def draft_ir(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        del inputs
        return {
            "artifact_ref": None,
            "reason_codes": ["draft_ir_graph_validation_failed"],
            "kernel_refusal": {
                "reason_code": "draft_ir_graph_validation_failed",
                "missing_inputs": [],
                "retryable": True,
                "blocked_by_budget": False,
                "blocked_by_invariant": False,
            },
            "rejected_graph_artifact_ref": {"artifact_path": "artifacts/rejected/rejected-001.json"},
            "rejected_graph_summary": {"status": "invalid", "error": "bad graph"},
        }


class _DraftIRV2(DraftIRProposer):
    def draft_ir(self, inputs: Mapping[str, Any]) -> dict[str, Any]:
        del inputs
        return {
            "artifact_ref": {"artifact_path": "artifacts/ir/ir-002.json"},
            "reason_codes": ["ir_drafted"],
        }


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
            renderer=services,
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
    assert ActionType.RENDER.value in result.tool_menu
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
    assert ActionType.RENDER.value in result.tool_menu
    assert ActionType.TX_AUDIT_TRANSCRIPT.value in result.tool_menu
    assert ActionType.TX_OPEN_TRANSCRIPT_SPANS.value in result.tool_menu
    assert ActionType.TX_VERIFY_TRANSCRIPT_WITH_IMAGE.value in result.tool_menu
    assert ActionType.TX_SAVE_TRANSCRIPT_SPAN_SEEDS.value in result.tool_menu
    assert ActionType.TX_APPLY_EDIT_PLAN.value in result.tool_menu
    assert ActionType.TX_PROMOTE_TRANSCRIPT_FOR_MAPPING.value in result.tool_menu
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


def test_update_latest_refs_clears_derived_refs_when_draft_ir_updates_ir_ref() -> None:
    run_artifact = RunArtifact(
        run_id="run-001",
        request_id="req-001",
        ir_artifact_ref=ArtifactRef(artifact_path="artifacts/ir/ir-v1.json"),
        compile_artifact_ref=ArtifactRef(artifact_path="artifacts/compile/c-v1.json"),
        judge_artifact_ref=ArtifactRef(artifact_path="artifacts/judge/j-v1.json"),
        bundle_artifact_ref=ArtifactRef(artifact_path="artifacts/bundle/b-v1.json"),
        georeference_artifact_ref=ArtifactRef(artifact_path="artifacts/georef/g-v1.json"),
    )
    step = StepRecord(
        step_id="step-draft-002",
        action=ActionType.DRAFT_IR,
        outputs={"ir_artifact_ref": {"artifact_path": "artifacts/ir/ir-v2.json"}},
        reason_codes=["ir_drafted"],
    )

    kernel_session_module._update_latest_refs(run_artifact, step)

    assert run_artifact.ir_artifact_ref is not None
    assert run_artifact.ir_artifact_ref.artifact_path == "artifacts/ir/ir-v2.json"
    assert run_artifact.compile_artifact_ref is None
    assert run_artifact.judge_artifact_ref is None
    assert run_artifact.bundle_artifact_ref is None
    assert run_artifact.georeference_artifact_ref is None


def test_dashboard_latest_refs_clear_stale_compile_judge_bundle_after_new_draft_ir() -> None:
    services = _DeterministicServices()
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            compiler=services,
            judge=services,
            bundler=services,
            validator=services,
            draft_ir_proposer=_DraftIRV2(),
        )
    )
    persistence = _InMemorySessionPersistence()
    manager = KernelSessionManager(action_executor=executor, persistence_service=persistence)
    started = manager.start_session(_start_request())
    assert started.session_id is not None

    compile_step = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-compile",
            action_type=ActionType.COMPILE,
            inputs={},
        )
    )
    judge_step = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-judge",
            action_type=ActionType.JUDGE,
            inputs={},
        )
    )
    bundle_step = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-bundle",
            action_type=ActionType.BUNDLE,
            inputs={},
        )
    )
    assert compile_step.dashboard.latest_refs.compile_ref is not None
    assert judge_step.dashboard.latest_refs.judge_ref is not None
    assert bundle_step.dashboard.latest_refs.bundle_ref is not None

    draft_step = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-draft",
            action_type=ActionType.DRAFT_IR,
            inputs={"dossier_id": "D1", "graph": {"graph_id": "g1", "nodes": [{"id": "n1", "kind": "point"}], "edges": [], "metadata": {}}},
        )
    )

    latest_refs = draft_step.dashboard.latest_refs
    assert latest_refs.ir_ref is not None
    assert latest_refs.ir_ref.get("artifact_path") == "artifacts/ir/ir-002.json"
    assert latest_refs.compile_ref is None
    assert latest_refs.judge_ref is None
    assert latest_refs.bundle_ref is None


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


def test_declare_done_requires_render_when_goal_render_required() -> None:
    manager, _ = _session_manager()
    started = manager.start_session(
        _start_request().model_copy(
            update={
                "goal": KernelGoal(
                    requires_global_placement=False,
                    render_required=True,
                    objective="session test render",
                )
            }
        )
    )
    assert started.session_id is not None

    manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-r-c",
            action_type=ActionType.COMPILE,
            inputs={},
        )
    )
    manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-r-j",
            action_type=ActionType.JUDGE,
            inputs={},
        )
    )
    refused = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-r-d0",
            action_type=ActionType.DECLARE_DONE,
            inputs={},
        )
    )
    assert refused.execution_state == StepExecutionState.REFUSED
    assert refused.refusal is not None
    assert "has_render" in refused.refusal.missing_inputs

    manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-r-render",
            action_type=ActionType.RENDER,
            inputs={"georef_artifact_ref": "artifacts/georef/g-001.json"},
        )
    )
    accepted = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-r-d1",
            action_type=ActionType.DECLARE_DONE,
            inputs={},
        )
    )
    assert accepted.execution_state == StepExecutionState.EXECUTED


def test_declare_done_acceptance_marks_final_feature_graph_pointers(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    original = kernel_session_module.FeatureGraphPersistenceService.mark_final_pointers_from_paths

    def _spy(self, *, ir_artifact_path: str | None, bundle_artifact_path: str | None = None):  # type: ignore[override]
        calls.append(
            {
                "ir_artifact_path": ir_artifact_path,
                "bundle_artifact_path": bundle_artifact_path,
            }
        )
        return {"success": True, "written": ["final_ir.json"]}

    monkeypatch.setattr(kernel_session_module.FeatureGraphPersistenceService, "mark_final_pointers_from_paths", _spy)
    try:
        manager, _ = _session_manager()
        started = manager.start_session(_start_request())
        assert started.session_id is not None
        manager.step(
            KernelStepRequest(
                session_id=started.session_id,
                idempotency_key="k-c1",
                action_type=ActionType.COMPILE,
                inputs={},
            )
        )
        manager.step(
            KernelStepRequest(
                session_id=started.session_id,
                idempotency_key="k-j1",
                action_type=ActionType.JUDGE,
                inputs={},
            )
        )
        accepted = manager.step(
            KernelStepRequest(
                session_id=started.session_id,
                idempotency_key="k-d1",
                action_type=ActionType.DECLARE_DONE,
                inputs={},
            )
        )
        assert accepted.execution_state == StepExecutionState.EXECUTED
        assert calls, "expected final pointer write attempt"
        assert isinstance(calls[0]["ir_artifact_path"], str)
    finally:
        monkeypatch.setattr(
            kernel_session_module.FeatureGraphPersistenceService,
            "mark_final_pointers_from_paths",
            original,
        )


def test_step_surfaces_tool_level_kernel_refusal_and_preserves_repair_outputs() -> None:
    services = _DeterministicServices()
    executor = ActionExecutor(
        deps=ActionExecutorDeps(
            draft_ir_proposer=_RefusingDraftIR(),
            compiler=services,
            judge=services,
            bundler=services,
            validator=services,
        )
    )
    persistence = _InMemorySessionPersistence()
    manager = KernelSessionManager(action_executor=executor, persistence_service=persistence)
    started = manager.start_session(_start_request())
    assert started.session_id is not None

    result = manager.step(
        KernelStepRequest(
            session_id=started.session_id,
            idempotency_key="k-draft-refuse",
            action_type=ActionType.DRAFT_IR,
            inputs={"dossier_id": "D1"},
        )
    )

    assert result.execution_state == StepExecutionState.REFUSED
    assert result.refusal is not None
    assert result.refusal.reason_code == "draft_ir_graph_validation_failed"
    assert result.step_record is not None
    outputs_inline = result.step_record.get("outputs_inline")
    assert isinstance(outputs_inline, dict)
    assert "rejected_graph_artifact_ref" in outputs_inline
    assert result.dashboard.latest_refs.ir_ref is not None  # initial_ir_ref remains intact
