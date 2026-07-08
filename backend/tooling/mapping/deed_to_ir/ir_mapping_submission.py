"""Submit saved IR artifacts for internal compile/judge/render mapping."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from feature_graph.artifact_refs import parse_feature_graph_artifact_ref
from feature_graph.artifacts import IRArtifact
from services.feature_graph.feature_graph_evaluation_service import FeatureGraphEvaluationService
from services.feature_graph.feature_graph_mapping_service import FeatureGraphMappingService
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_mapping_submission_service import (
    FeatureGraphMappingSubmissionService,
)
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .artifact_hydration import image_evidence_from_png_path, resolve_sidecar_path_for_ref
from .mapping_review import build_mapping_review_from_mapping_artifact
from .mapping_sanity import attach_sanity_review_to_mapping_review, build_operand_evidence_index
from .correction_posture import attach_correction_posture_to_mapping_review


def submit_ir_for_mapping(
    *,
    dossier_id: str,
    ir_artifact_ref: str,
    persistence: FeatureGraphPersistenceService | None = None,
    submission: FeatureGraphMappingSubmissionService | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
    handoff_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not dossier_id:
        raise ValueError("dossier_id_required")
    parsed = _parse_ir_ref(ir_artifact_ref)
    if parsed is None:
        return _refusal("ir_artifact_ref_invalid", "ir_artifact_ref must be a canonical feature_graph:ir ref.")
    _, ir_artifact_id = parsed
    service = persistence or FeatureGraphPersistenceService()
    raw = service.get_artifact(dossier_id, ir_artifact_id)
    if not isinstance(raw, dict):
        return _refusal("ir_artifact_not_found", "IR artifact was not found in the current dossier.")
    try:
        ir_artifact = IRArtifact.model_validate(raw)
    except Exception:
        return _refusal("ir_artifact_invalid", "Stored IR artifact payload failed validation.")
    if str(raw.get("artifact_type") or "") != "ir":
        return _refusal("ir_artifact_type_mismatch", "Ref must point to an IR artifact.")

    submitter = submission or _default_submission_service(service)
    outcome = submitter.submit_ir_artifact(ir_artifact=ir_artifact, dossier_id=dossier_id)
    mapping = outcome.mapping
    compile_outcome = outcome.evaluation.compile_outcome
    judge_outcome = outcome.evaluation.judge_outcome
    artifact = mapping.artifact

    image_evidence: list[dict[str, Any]] = []
    for descriptor, label in (
        (artifact.clean_render, "clean_render"),
        (artifact.control_render, "control_render"),
    ):
        evidence = _image_evidence_for_sidecar_ref(
            dossier_id=dossier_id,
            ref_id=descriptor.ref,
            persistence=service,
        )
        if evidence is not None:
            image_evidence.append(evidence)

    artifact_refs = [
        mapping.artifact_ref,
        artifact.control_render.ref,
        artifact.clean_render.ref,
        artifact.geometry.ref,
        compile_outcome.artifact_ref,
        judge_outcome.artifact_ref,
        outcome.ir_artifact_ref,
    ]

    mapping_review = build_mapping_review_from_mapping_artifact(
        mapping=artifact,
        mapping_artifact_ref=mapping.artifact_ref,
        compiled_feature_count=compile_outcome.compiled_feature_count,
        rendered_feature_count=mapping.rendered_feature_count,
        skipped_feature_count=mapping.skipped_feature_count,
        compile_gap_count=len(compile_outcome.artifact.gaps),
        judge_gap_count=len(judge_outcome.artifact.report.gaps),
    )
    attach_sanity_review_to_mapping_review(
        mapping_review,
        graph=ir_artifact.graph,
        compile_artifact=compile_outcome.artifact,
        operand_evidence_index=_resolve_operand_evidence_index(
            resolution_state_snapshot=resolution_state_snapshot,
            handoff_context=handoff_context,
        ),
    )
    attach_correction_posture_to_mapping_review(
        mapping_review,
        resolution_state_snapshot=resolution_state_snapshot
        if isinstance(resolution_state_snapshot, Mapping)
        else (
            handoff_context.get("resolution_state_snapshot")
            if isinstance(handoff_context, Mapping)
            and isinstance(handoff_context.get("resolution_state_snapshot"), Mapping)
            else None
        ),
        ir_graph=ir_artifact.graph,
        compile_artifact=compile_outcome.artifact,
        ir_artifact_ref=outcome.ir_artifact_ref,
    )
    from .draft_patch_targets import attach_draft_patch_targets_to_mapping_review

    attach_draft_patch_targets_to_mapping_review(
        mapping_review,
        base_draft_ref=outcome.ir_artifact_ref,
    )
    lineage_lock = {
        "source_ir_artifact_ref": outcome.ir_artifact_ref,
        "mapping_artifact_ref": mapping.artifact_ref,
        "use_these_refs_for_next_preview": True,
    }
    mapping_review["lineage_lock"] = lineage_lock

    return {
        "executed": True,
        "artifact_refs": artifact_refs,
        "image_evidence": image_evidence,
        "outputs": {
            "mapping_artifact_ref": mapping.artifact_ref,
            "compile_artifact_ref": compile_outcome.artifact_ref,
            "judge_artifact_ref": judge_outcome.artifact_ref,
            "geometry_ref": artifact.geometry.ref,
            "clean_render_ref": artifact.clean_render.ref,
            "control_render_ref": artifact.control_render.ref,
            "graph_id": mapping.graph_id,
            "compiled_feature_count": compile_outcome.compiled_feature_count,
            "rendered_feature_count": mapping.rendered_feature_count,
            "skipped_feature_count": mapping.skipped_feature_count,
            "compile_gap_count": len(compile_outcome.artifact.gaps),
            "judge_gap_count": len(judge_outcome.artifact.report.gaps),
            "warning_count": mapping.warning_count,
            "coordinate_space": artifact.coordinate_space,
            "world_bbox": artifact.world_bbox.model_dump(mode="json"),
            "mapping_review": mapping_review,
            "lineage_lock": lineage_lock,
        },
    }


def _resolve_operand_evidence_index(
    *,
    resolution_state_snapshot: Mapping[str, Any] | None,
    handoff_context: Mapping[str, Any] | None,
) -> dict[str, list[str]] | None:
    snapshot = resolution_state_snapshot
    if snapshot is None and isinstance(handoff_context, Mapping):
        raw = handoff_context.get("resolution_state_snapshot")
        if isinstance(raw, Mapping):
            snapshot = raw
    if snapshot is None:
        return None
    index = build_operand_evidence_index(snapshot)
    return index or None


def _default_submission_service(
    persistence: FeatureGraphPersistenceService,
) -> FeatureGraphMappingSubmissionService:
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=persistence.artifacts_root)
    evaluation = FeatureGraphEvaluationService(persistence)
    mapping = FeatureGraphMappingService(persistence=persistence, sidecars=sidecars)
    return FeatureGraphMappingSubmissionService(evaluation=evaluation, mapping=mapping)


def _parse_ir_ref(ref: str) -> tuple[str, str] | None:
    try:
        artifact_type, artifact_id = parse_feature_graph_artifact_ref(ref)
    except ValueError:
        return None
    if artifact_type != "ir":
        return None
    return artifact_type, artifact_id


def _image_evidence_for_sidecar_ref(
    *,
    dossier_id: str,
    ref_id: str,
    persistence: FeatureGraphPersistenceService,
) -> dict[str, Any] | None:
    try:
        path = resolve_sidecar_path_for_ref(
            dossier_id=dossier_id,
            ref_id=ref_id,
            artifacts_root=persistence.artifacts_root,
        )
    except ValueError:
        return None
    if path.suffix.lower() != ".png":
        return None
    return image_evidence_from_png_path(ref_id=ref_id, path=path)


def _refusal(code: str, message: str) -> dict[str, Any]:
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": False,
            "blocked_by_invariant": True,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {"error": {"code": code, "message": message}},
    }
