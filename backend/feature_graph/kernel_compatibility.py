"""Product-owned legacy compatibility loop for Agent Kernel v0.

This module keeps the deed/feature-graph progression grammar outside the shared kernel package.
The shared ``agent_kernel.kernel`` module delegates here for legacy JSON-in/JSON-out callers.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional

from backend.agent_kernel.actions import ActionExecutor
from backend.agent_kernel.budgets import BudgetStatus, BudgetTracker
from backend.agent_kernel.harness_action_ids import ActionType, canonical_action_id
from backend.agent_kernel.kernel import (
    IRGraphLoader,
    KernelLoopOutput,
    RunArtifactPersistence,
    _classify_terminal_outcome,
    _coerce_graph_payload,
    _extract_artifact_ref,
    _find_missing_capability_reason,
    _find_worker_unavailable_reason,
)
from backend.agent_kernel.models import (
    KernelRequest,
    KernelResult,
    KernelState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from backend.agent_kernel.no_progress import (
    GapSignal,
    NoProgressDetector,
    compute_artifact_digests,
    compute_gap_signature,
)
from backend.agent_kernel.policies import DefaultKernelPolicy, KernelPolicy
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, StepRecord
from backend.agent_kernel.state_machine import KernelEvent, advance_state


class FileSystemIRGraphLoader:
    """Default filesystem-based loader for IR/graph JSON artifacts."""

    def load_graph(self, ir_artifact_ref: ArtifactRef) -> dict[str, object]:
        payload = json.loads(Path(ir_artifact_ref.artifact_path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            graph_payload = payload.get("graph")
            if isinstance(graph_payload, dict):
                return graph_payload
            return payload
        raise ValueError("ir_artifact_payload_not_object")


def run_feature_graph_compatibility_kernel(
    request: KernelRequest,
    *,
    policy: KernelPolicy | None = None,
    action_executor: ActionExecutor | None = None,
    persistence_service: RunArtifactPersistence | None = None,
    ir_graph_loader: IRGraphLoader | None = None,
    no_progress_max_stagnant_repair_cycles: int = 2,
    run_id_factory: Callable[[KernelRequest], str] | None = None,
) -> KernelLoopOutput:
    """Legacy product workflow loop kept for compatibility callers."""

    if policy is None:
        policy = DefaultKernelPolicy()
    if action_executor is None:
        action_executor = ActionExecutor()
    ir_graph_loader = ir_graph_loader or FileSystemIRGraphLoader()
    run_id_factory = run_id_factory or (lambda req: f"{req.request_id}-run-001")
    budget_tracker = BudgetTracker(request.budgets)
    no_progress = NoProgressDetector(max_stagnant_repair_cycles=no_progress_max_stagnant_repair_cycles)
    run_artifact = RunArtifact(
        run_id=run_id_factory(request),
        request_id=request.request_id,
        ir_artifact_ref=(
            ArtifactRef(artifact_path=request.initial_ir_ref)
            if request.initial_ir_ref is not None
            else None
        ),
    )
    current_graph = _coerce_graph_payload(request.initial_graph_json)
    state = KernelState.INIT
    step_index = 0
    stop_reason = StopReason.INTERNAL_ERROR
    reason_code: Optional[str] = "kernel_uninitialized"

    if run_artifact.ir_artifact_ref is None and current_graph is None:
        stop_reason = StopReason.NEEDS_UPLOAD
        reason_code = "missing_initial_ir_ref_or_graph_json"
        return _finalize(request, run_artifact, state, stop_reason, reason_code, persistence_service)

    if request.goal.requires_global_placement:
        if run_artifact.ir_artifact_ref is not None:
            try:
                ir_graph = ir_graph_loader.load_graph(run_artifact.ir_artifact_ref)
            except (FileNotFoundError, json.JSONDecodeError, ValueError):
                stop_reason = StopReason.INTERNAL_ERROR
                reason_code = "initial_ir_load_failed"
                return _finalize(request, run_artifact, state, stop_reason, reason_code, persistence_service)
        else:
            ir_graph = current_graph if current_graph is not None else {}

        step_index += 1
        set_requirements_inputs = {
            "graph": ir_graph,
            "global_placement_required": True,
        }
        if run_artifact.ir_artifact_ref is not None:
            set_requirements_inputs["updated_ir_artifact_ref"] = run_artifact.ir_artifact_ref.model_dump(
                mode="json"
            )
        step = action_executor.execute(
            step_id=f"step-{step_index:03d}",
            action=ActionType.SET_GRAPH_REQUIREMENTS,
            inputs=set_requirements_inputs,
        )
        status = _record_step(run_artifact, step, budget_tracker)
        run_artifact.ir_artifact_ref = _extract_artifact_ref(step.outputs, "ir_artifact_ref")
        step_graph = step.outputs.get("graph")
        if isinstance(step_graph, dict):
            current_graph = step_graph
        state = advance_state(state, KernelEvent.SOURCE_READY)
        if status.exceeded:
            stop_reason = StopReason.BUDGET_EXCEEDED
            reason_code = status.reason_code
            return _finalize(request, run_artifact, state, stop_reason, reason_code, persistence_service)
    else:
        state = advance_state(state, KernelEvent.SOURCE_READY)

    while state != KernelState.DONE:
        status = budget_tracker.check()
        if status.exceeded:
            stop_reason = StopReason.BUDGET_EXCEEDED
            reason_code = status.reason_code
            break

        if state == KernelState.SOURCE_READY:
            if request.goal.requires_global_placement and run_artifact.retrieval_artifact_ref is None:
                step_index += 1
                retrieval_inputs = {"semantic": True, "graph": current_graph}
                if run_artifact.ir_artifact_ref is not None:
                    retrieval_inputs["ir_artifact_ref"] = run_artifact.ir_artifact_ref.model_dump(mode="json")
                retrieval_step = action_executor.execute(
                    step_id=f"step-{step_index:03d}",
                    action=ActionType.RETRIEVE_EVIDENCE,
                    inputs=retrieval_inputs,
                )
                status = _record_step(run_artifact, retrieval_step, budget_tracker)
                run_artifact.retrieval_artifact_ref = _extract_artifact_ref(
                    retrieval_step.outputs,
                    "retrieval_artifact_ref",
                )
                if status.exceeded:
                    stop_reason = StopReason.BUDGET_EXCEEDED
                    reason_code = status.reason_code
                    break
                unavailable_reason = _find_worker_unavailable_reason(retrieval_step.reason_codes)
                if unavailable_reason is not None and run_artifact.retrieval_artifact_ref is None:
                    stop_reason = StopReason.WORKER_UNAVAILABLE
                    reason_code = unavailable_reason
                    break

            step_index += 1
            compile_inputs = {"graph": current_graph}
            if run_artifact.ir_artifact_ref is not None:
                compile_inputs["ir_artifact_ref"] = run_artifact.ir_artifact_ref.model_dump(mode="json")
            step = action_executor.execute(
                step_id=f"step-{step_index:03d}",
                action=ActionType.COMPILE_ARTIFACT,
                inputs=compile_inputs,
            )
            status = _record_step(run_artifact, step, budget_tracker)
            run_artifact.compile_artifact_ref = _extract_artifact_ref(step.outputs, "compile_artifact_ref")
            capability_gap_reason = _find_missing_capability_reason(step.reason_codes)
            if run_artifact.compile_artifact_ref is None and capability_gap_reason is not None:
                stop_reason = StopReason.NEEDS_CAPABILITY
                reason_code = capability_gap_reason
                break
            state = advance_state(state, KernelEvent.ANALYSIS_COMPLETED)
            if status.exceeded:
                stop_reason = StopReason.BUDGET_EXCEEDED
                reason_code = status.reason_code
                break
            continue

        if state == KernelState.ANALYZED:
            step_index += 1
            judge_inputs = {
                "compile_artifact_ref": run_artifact.compile_artifact_ref.model_dump(mode="json")
                if run_artifact.compile_artifact_ref is not None
                else None,
                "graph": current_graph,
            }
            if run_artifact.ir_artifact_ref is not None:
                judge_inputs["ir_artifact_ref"] = run_artifact.ir_artifact_ref.model_dump(mode="json")
            step = action_executor.execute(
                step_id=f"step-{step_index:03d}",
                action=ActionType.JUDGE_ARTIFACT,
                inputs=judge_inputs,
            )
            status = _record_step(run_artifact, step, budget_tracker)
            run_artifact.judge_artifact_ref = _extract_artifact_ref(step.outputs, "judge_artifact_ref")
            capability_gap_reason = _find_missing_capability_reason(step.reason_codes)
            if run_artifact.judge_artifact_ref is None and capability_gap_reason is not None:
                stop_reason = StopReason.NEEDS_CAPABILITY
                reason_code = capability_gap_reason
                break
            state = advance_state(state, KernelEvent.REVIEW_COMPLETED)
            if status.exceeded:
                stop_reason = StopReason.BUDGET_EXCEEDED
                reason_code = status.reason_code
                break
            continue

        if state == KernelState.PACKAGE_READY:
            step_index += 1
            bundle_step = action_executor.execute(
                step_id=f"step-{step_index:03d}",
                action=ActionType.BUNDLE_ARTIFACT,
                inputs={
                    "compile_artifact_ref": run_artifact.compile_artifact_ref.model_dump(mode="json")
                    if run_artifact.compile_artifact_ref is not None
                    else None,
                    "judge_artifact_ref": run_artifact.judge_artifact_ref.model_dump(mode="json")
                    if run_artifact.judge_artifact_ref is not None
                    else None,
                },
            )
            status = _record_step(run_artifact, bundle_step, budget_tracker)
            run_artifact.bundle_artifact_ref = _extract_artifact_ref(bundle_step.outputs, "bundle_artifact_ref")
            capability_gap_reason = _find_missing_capability_reason(bundle_step.reason_codes)
            if run_artifact.bundle_artifact_ref is None and capability_gap_reason is not None:
                stop_reason = StopReason.NEEDS_CAPABILITY
                reason_code = capability_gap_reason
                break
            if status.exceeded:
                stop_reason = StopReason.BUDGET_EXCEEDED
                reason_code = status.reason_code
                break

            step_index += 1
            georef_step = action_executor.execute(
                step_id=f"step-{step_index:03d}",
                action=ActionType.GEOREFERENCE_ARTIFACT,
                inputs={
                    "bundle_artifact_ref": run_artifact.bundle_artifact_ref.model_dump(mode="json")
                    if run_artifact.bundle_artifact_ref is not None
                    else None
                },
            )
            status = _record_step(run_artifact, georef_step, budget_tracker)
            capability_gap_reason = _find_missing_capability_reason(georef_step.reason_codes)
            if capability_gap_reason is not None:
                stop_reason = StopReason.NEEDS_CAPABILITY
                reason_code = capability_gap_reason
                break
            if status.exceeded:
                stop_reason = StopReason.BUDGET_EXCEEDED
                reason_code = status.reason_code
                break

            step_index += 1
            validate_step = action_executor.execute(
                step_id=f"step-{step_index:03d}",
                action=ActionType.VALIDATE_ARTIFACT,
                inputs={
                    "bundle_artifact_ref": run_artifact.bundle_artifact_ref.model_dump(mode="json")
                    if run_artifact.bundle_artifact_ref is not None
                    else None
                },
            )
            status = _record_step(run_artifact, validate_step, budget_tracker)
            capability_gap_reason = _find_missing_capability_reason(validate_step.reason_codes)
            if capability_gap_reason is not None:
                stop_reason = StopReason.NEEDS_CAPABILITY
                reason_code = capability_gap_reason
                break
            if status.exceeded:
                stop_reason = StopReason.BUDGET_EXCEEDED
                reason_code = status.reason_code
                break

            validation_passed = bool(
                validate_step.validation_result is not None and validate_step.validation_result.passed
            )
            if validation_passed:
                state = advance_state(state, KernelEvent.PACKAGE_COMMITTED)
                state = advance_state(state, KernelEvent.FINISH)
                stop_reason = StopReason.COMPLETED
                reason_code = "kernel_completed"
                break

            state = advance_state(state, KernelEvent.REPAIR_REQUESTED)
            gap_code = (
                validate_step.validation_result.reason_code
                if validate_step.validation_result is not None
                and validate_step.validation_result.reason_code is not None
                else "validation_failure"
            )
            gap_signature = compute_gap_signature(
                [GapSignal(gap_code=gap_code, base_score=1.0)],
                policy,
            )
            artifact_digests = compute_artifact_digests(
                {
                    "ir": run_artifact.ir_artifact_ref,
                    "compile": run_artifact.compile_artifact_ref,
                    "judge": run_artifact.judge_artifact_ref,
                    "bundle": run_artifact.bundle_artifact_ref,
                }
            )
            no_progress_status = no_progress.evaluate_repair_cycle(
                gap_signature=gap_signature,
                artifact_digests=artifact_digests,
            )
            if no_progress_status.detected:
                stop_reason = StopReason.VALIDATION_FAILED
                reason_code = gap_code
                break

            step_index += 1
            patch_step = action_executor.execute(
                step_id=f"step-{step_index:03d}",
                action=ActionType.PROPOSE_PATCH,
                inputs={"reason_code": gap_code},
            )
            status = _record_step(run_artifact, patch_step, budget_tracker)
            if status.exceeded:
                stop_reason = StopReason.BUDGET_EXCEEDED
                reason_code = status.reason_code
                break

            capability_gap_reason = _find_missing_capability_reason(patch_step.reason_codes)
            if capability_gap_reason is not None:
                stop_reason = StopReason.VALIDATION_FAILED
                reason_code = gap_code
                break

            state = advance_state(state, KernelEvent.REPAIR_COMPLETED)
            continue

        stop_reason = StopReason.INTERNAL_ERROR
        reason_code = f"unsupported_state:{state.value}"
        break

    return _finalize(request, run_artifact, state, stop_reason, reason_code, persistence_service)


def _record_step(
    run_artifact: RunArtifact,
    step: StepRecord,
    budget_tracker: BudgetTracker,
) -> BudgetStatus:
    run_artifact.steps.append(step)
    step_action = canonical_action_id(step.action)
    if step_action == ActionType.RETRIEVE_EVIDENCE.value:
        budget_tracker.record_retrieval_call(semantic=bool(step.inputs.get("semantic", False)))
    if step_action == ActionType.PROPOSE_PATCH.value:
        budget_tracker.record_patch_call()
    return budget_tracker.record_step()


def _finalize(
    request: KernelRequest,
    run_artifact: RunArtifact,
    final_state: KernelState,
    stop_reason: StopReason,
    reason_code: str | None,
    persistence_service: RunArtifactPersistence | None,
) -> KernelLoopOutput:
    run_artifact_ref: Optional[str] = None
    if persistence_service is not None:
        persisted = persistence_service.save_run_artifact(run_artifact)
        run_artifact_ref = str(persisted.get("path"))

    terminal_outcome = _classify_terminal_outcome(stop_reason)
    terminal = TerminalOutcome(
        terminal_outcome=terminal_outcome,
        stop_reason=stop_reason,
        success=terminal_outcome == TerminalOutcomeKind.SUCCESS,
        reason_code=reason_code,
    )
    kernel_result = KernelResult(
        request_id=request.request_id,
        final_state=final_state,
        terminal=terminal,
        steps_executed=len(run_artifact.steps),
        run_artifact_ref=run_artifact_ref,
    )
    return KernelLoopOutput(kernel_result=kernel_result, run_artifact=run_artifact)
