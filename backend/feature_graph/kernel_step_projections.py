"""Feature-graph / deed-to-IR step result projection (Phase 34).

Maps harness action ids used by the deed→IR toolchain into ``RunArtifact`` ref slots.
Owned by the feature-graph domain — not ``agent_kernel.session``.
"""

from __future__ import annotations

from agent_kernel.actions import ProviderStepResultProjector
from agent_kernel.harness_action_ids import ActionType
from agent_kernel.ref_coercion import extract_output_ref
from agent_kernel.run_artifact import RunArtifact, StepRecord


def project_feature_graph_deed_step(run_artifact: RunArtifact, step: StepRecord) -> None:
    """Update deed/FG artifact refs from one executed step (output-key semantics are domain-owned)."""
    a = step.action
    if a == ActionType.SET_GRAPH_REQUIREMENTS.value:
        run_artifact.ir_artifact_ref = extract_output_ref(step.outputs, "ir_artifact_ref") or run_artifact.ir_artifact_ref
    if a == ActionType.DRAFT_IR.value:
        previous_ir_ref = run_artifact.ir_artifact_ref
        next_ir_ref = extract_output_ref(step.outputs, "ir_artifact_ref")
        if next_ir_ref is not None:
            ir_changed = previous_ir_ref is None or previous_ir_ref.artifact_path != next_ir_ref.artifact_path
            run_artifact.ir_artifact_ref = next_ir_ref
            if ir_changed:
                run_artifact.compile_artifact_ref = None
                run_artifact.judge_artifact_ref = None
                run_artifact.bundle_artifact_ref = None
                run_artifact.georeference_artifact_ref = None
                run_artifact.validate_artifact_ref = None
                run_artifact.render_artifact_ref = None
    if a == ActionType.RETRIEVE_EVIDENCE.value:
        run_artifact.retrieval_artifact_ref = extract_output_ref(step.outputs, "retrieval_artifact_ref")
    if a == ActionType.UPSERT_ARTIFACT_SPAN_INDEX.value:
        run_artifact.deed_span_index_artifact_ref = extract_output_ref(step.outputs, "artifact_span_index_ref")
    if a == ActionType.COMPILE.value:
        run_artifact.compile_artifact_ref = extract_output_ref(step.outputs, "compile_artifact_ref")
    if a == ActionType.JUDGE.value:
        run_artifact.judge_artifact_ref = extract_output_ref(step.outputs, "judge_artifact_ref")
    if a == ActionType.BUNDLE.value:
        run_artifact.bundle_artifact_ref = extract_output_ref(step.outputs, "bundle_artifact_ref")
    if a == ActionType.GEOREFERENCE.value:
        run_artifact.georeference_artifact_ref = extract_output_ref(step.outputs, "georeference_artifact_ref")
        run_artifact.validate_artifact_ref = None
        run_artifact.render_artifact_ref = None
    if a == ActionType.VALIDATE.value:
        run_artifact.validate_artifact_ref = extract_output_ref(step.outputs, "validate_artifact_ref")
    if a == ActionType.RENDER.value:
        run_artifact.render_artifact_ref = extract_output_ref(step.outputs, "render_artifact_ref")


def build_feature_graph_provider_step_projectors() -> dict[str, ProviderStepResultProjector]:
    fn: ProviderStepResultProjector = project_feature_graph_deed_step
    return {
        ActionType.SET_GRAPH_REQUIREMENTS.value: fn,
        ActionType.DRAFT_IR.value: fn,
        ActionType.RETRIEVE_EVIDENCE.value: fn,
        ActionType.UPSERT_ARTIFACT_SPAN_INDEX.value: fn,
        ActionType.COMPILE.value: fn,
        ActionType.JUDGE.value: fn,
        ActionType.BUNDLE.value: fn,
        ActionType.GEOREFERENCE.value: fn,
        ActionType.VALIDATE.value: fn,
        ActionType.RENDER.value: fn,
    }
