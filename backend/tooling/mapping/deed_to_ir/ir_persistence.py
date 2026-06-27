"""IR artifact persistence for deed-to-IR (draft save + compile/judge feedback)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from feature_graph.artifact_refs import (
    ARTIFACT_REF_PREFIXES,
    build_feature_graph_artifact_ref,
)
from feature_graph.artifacts import create_ir_artifact
from feature_graph.models import FeatureGraph
from pydantic import ValidationError

from services.feature_graph.feature_graph_evaluation_service import FeatureGraphEvaluationService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .draft_ir_lifecycle import (
    build_current_draft_ir,
    build_draft_source_metadata,
    build_evaluation_feedback,
    compute_draft_structural_metrics,
    draft_scope_key,
    draft_scope_output_fields,
    load_base_draft_artifact,
    prior_draft_sequence_index_from_artifact,
    prior_graph_id_from_artifact,
    resolve_draft_sequence_index,
    resolve_next_draft_sequence_index,
    run_draft_compile_judge,
    stable_draft_artifact_id,
)

IR_REF_PREFIX = ARTIFACT_REF_PREFIXES["ir"]
_MAX_VALIDATION_ERRORS = 24
_VALIDATION_FAILURE_REASON = "feature_graph_validation_failed"
_DRAFT_GRAPH_ID_MISMATCH = "draft_graph_id_mismatch"


def save_ir_artifact(
    *,
    dossier_id: str,
    feature_graph: dict[str, Any],
    artifact_id: str | None = None,
    base_draft_ref: str | None = None,
    source_document_id: str | None = None,
    created_by: str | None = None,
    draft_workspace_id: str | None = None,
    draft_run_id: str | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
    evaluation: FeatureGraphEvaluationService | None = None,
) -> dict[str, Any]:
    """Validate and persist a draft FeatureGraph IR checkpoint with compile/judge feedback."""
    if not dossier_id:
        raise ValueError("dossier_id_required")
    if not isinstance(feature_graph, dict):
        return _validation_failure(["feature_graph must be an object"])
    try:
        graph = FeatureGraph.model_validate(feature_graph)
    except ValidationError as exc:
        return _validation_failure(_format_validation_errors(exc))

    service = persistence or FeatureGraphPersistenceService()
    scoped_key = draft_scope_key(workspace_id=draft_workspace_id, run_id=draft_run_id)

    if isinstance(base_draft_ref, str) and base_draft_ref.strip():
        prior_artifact, base_error = load_base_draft_artifact(
            persistence=service,
            dossier_id=dossier_id,
            base_draft_ref=base_draft_ref.strip(),
            draft_workspace_id=draft_workspace_id,
            draft_run_id=draft_run_id,
        )
        if base_error:
            return _base_draft_refusal(
                reason_code=base_error,
                message=f"Could not load base draft ref: {base_error}",
            )
        expected_graph_id = prior_graph_id_from_artifact(prior_artifact)  # type: ignore[arg-type]
        if expected_graph_id and expected_graph_id != graph.graph_id:
            return _graph_id_mismatch_refusal(
                expected_graph_id=expected_graph_id,
                actual_graph_id=graph.graph_id,
            )
        draft_sequence_index = resolve_next_draft_sequence_index(
            persistence=service,
            dossier_id=dossier_id,
            graph_id=graph.graph_id,
            base_prior_index=prior_draft_sequence_index_from_artifact(prior_artifact),  # type: ignore[arg-type]
            draft_scope_key=scoped_key,
        )
    else:
        draft_sequence_index = resolve_next_draft_sequence_index(
            persistence=service,
            dossier_id=dossier_id,
            graph_id=graph.graph_id,
            draft_scope_key=scoped_key,
        )
        if isinstance(artifact_id, str) and artifact_id.strip():
            explicit_index = resolve_draft_sequence_index(
                persistence=service,
                dossier_id=dossier_id,
                graph_id=graph.graph_id,
                artifact_id=_sanitize_artifact_id(artifact_id.strip()),
            )
            draft_sequence_index = max(draft_sequence_index, explicit_index)

    if isinstance(artifact_id, str) and artifact_id.strip():
        resolved_artifact_id = _sanitize_artifact_id(artifact_id.strip())
    else:
        resolved_artifact_id = stable_draft_artifact_id(
            graph.graph_id,
            draft_sequence_index,
            draft_scope_key=scoped_key,
        )
        existing = service.get_artifact(dossier_id, resolved_artifact_id)
        if isinstance(existing, Mapping):
            return _draft_artifact_exists_refusal(
                graph_id=graph.graph_id,
                artifact_id=resolved_artifact_id,
                latest_draft_ref=_latest_draft_ref_for_graph(
                    service,
                    dossier_id=dossier_id,
                    graph_id=graph.graph_id,
                    draft_scope_key=scoped_key,
                ),
            )

    source_metadata = build_draft_source_metadata(
        graph_id=graph.graph_id,
        draft_sequence_index=draft_sequence_index,
        draft_workspace_id=draft_workspace_id,
        draft_run_id=draft_run_id,
    )
    draft_version = source_metadata["draft_version"]
    artifact = create_ir_artifact(
        artifact_id=resolved_artifact_id,
        graph=graph,
        created_by=created_by or "deed_to_ir_agent",
        source_document_id=source_document_id,
    )
    artifact.source_metadata = source_metadata
    service.save_artifact(artifact, dossier_id=dossier_id)

    ir_ref = build_feature_graph_artifact_ref("ir", resolved_artifact_id)
    eval_service = evaluation or FeatureGraphEvaluationService(service)
    evaluation_artifacts, evaluation_warning = run_draft_compile_judge(
        evaluation=eval_service,
        ir_artifact=artifact,
        dossier_id=dossier_id,
    )
    compile_outcome = evaluation_artifacts.compile_outcome if evaluation_artifacts else None
    judge_outcome = evaluation_artifacts.judge_outcome if evaluation_artifacts else None
    structural_metrics = compute_draft_structural_metrics(graph)
    evaluation_feedback = build_evaluation_feedback(
        compile_outcome=compile_outcome,
        judge_outcome=judge_outcome,
        structural_metrics=structural_metrics,
        graph=graph,
    )
    current_draft_ir = build_current_draft_ir(
        graph=graph,
        ir_artifact_ref=ir_ref,
        draft_version=str(draft_version),
        draft_sequence_index=draft_sequence_index,
        evaluation_feedback=evaluation_feedback,
        evaluation_warning=evaluation_warning,
        structural_metrics=structural_metrics,
    )

    artifact_refs = [ir_ref]
    if evaluation_feedback.get("compile_artifact_ref"):
        artifact_refs.append(str(evaluation_feedback["compile_artifact_ref"]))
    if evaluation_feedback.get("judge_artifact_ref"):
        artifact_refs.append(str(evaluation_feedback["judge_artifact_ref"]))

    outputs: dict[str, Any] = {
        "ir_artifact_ref": ir_ref,
        "draft_ir_ref": ir_ref,
        "working_draft_ref": ir_ref,
        "draft_version": draft_version,
        "draft_sequence_index": draft_sequence_index,
        "is_draft": True,
        "artifact_id": resolved_artifact_id,
        "graph_id": graph.graph_id,
        "validation_errors": [],
        "current_draft_ir": current_draft_ir,
        **draft_scope_output_fields(
            draft_workspace_id=draft_workspace_id,
            draft_run_id=draft_run_id,
        ),
        **evaluation_feedback,
    }
    if evaluation_warning:
        outputs["evaluation_warning"] = evaluation_warning

    return {
        "executed": True,
        "artifact_refs": artifact_refs,
        "outputs": outputs,
    }


def _sanitize_artifact_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned[:128] or "ir_artifact"


def _validation_failure(errors: list[str]) -> dict[str, Any]:
    bounded = errors[:_MAX_VALIDATION_ERRORS]
    if len(errors) > _MAX_VALIDATION_ERRORS:
        bounded.append(f"... and {len(errors) - _MAX_VALIDATION_ERRORS} more validation errors")
    return {
        "executed": False,
        "reason_codes": [_VALIDATION_FAILURE_REASON],
        "refusal": {
            "reason_code": _VALIDATION_FAILURE_REASON,
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
            "missing_inputs": [],
        },
        "outputs": {
            "validation_errors": bounded,
            "ir_artifact_ref": None,
            "draft_ir_ref": None,
            "draft_version": None,
            "draft_sequence_index": None,
            "is_draft": None,
            "graph_id": None,
            "node_count": 0,
            "edge_count": 0,
            "source_entity_link_count": 0,
        },
    }


def _graph_id_mismatch_refusal(*, expected_graph_id: str, actual_graph_id: str) -> dict[str, Any]:
    return {
        "executed": False,
        "reason_codes": [_DRAFT_GRAPH_ID_MISMATCH],
        "refusal": {
            "reason_code": _DRAFT_GRAPH_ID_MISMATCH,
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
            "missing_inputs": [],
        },
        "outputs": {
            "expected_graph_id": expected_graph_id,
            "actual_graph_id": actual_graph_id,
            "ir_artifact_ref": None,
            "draft_ir_ref": None,
            "working_draft_ref": None,
            "draft_version": None,
            "draft_sequence_index": None,
            "is_draft": None,
            "graph_id": actual_graph_id,
            "validation_errors": [],
        },
    }


def _base_draft_refusal(*, reason_code: str, message: str) -> dict[str, Any]:
    return {
        "executed": False,
        "reason_codes": [reason_code],
        "refusal": {
            "reason_code": reason_code,
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
            "missing_inputs": [],
        },
        "outputs": {
            "message": message,
            "ir_artifact_ref": None,
            "draft_ir_ref": None,
            "working_draft_ref": None,
            "draft_version": None,
            "draft_sequence_index": None,
            "is_draft": None,
            "graph_id": None,
            "validation_errors": [],
        },
    }


def _draft_artifact_exists_refusal(
    *,
    graph_id: str,
    artifact_id: str,
    latest_draft_ref: str | None,
) -> dict[str, Any]:
    return {
        "executed": False,
        "reason_codes": ["draft_artifact_exists"],
        "refusal": {
            "reason_code": "draft_artifact_exists",
            "retryable": True,
            "blocked_by_budget": False,
            "blocked_by_invariant": False,
            "missing_inputs": [],
        },
        "outputs": {
            "graph_id": graph_id,
            "artifact_id": artifact_id,
            "latest_draft_ref": latest_draft_ref,
            "working_draft_ref": latest_draft_ref,
            "ir_artifact_ref": None,
            "draft_ir_ref": None,
            "draft_version": None,
            "draft_sequence_index": None,
            "is_draft": None,
            "validation_errors": [],
        },
    }


def _latest_draft_ref_for_graph(
    persistence: FeatureGraphPersistenceService,
    *,
    dossier_id: str,
    graph_id: str,
    draft_scope_key: str | None = None,
) -> str | None:
    from .draft_ir_lifecycle import max_draft_sequence_index_for_graph, stable_draft_artifact_id

    highest = max_draft_sequence_index_for_graph(
        persistence=persistence,
        dossier_id=dossier_id,
        graph_id=graph_id,
        draft_scope_key=draft_scope_key,
    )
    if highest < 0:
        return None
    artifact_id = stable_draft_artifact_id(
        graph_id,
        highest,
        draft_scope_key=draft_scope_key,
    )
    return build_feature_graph_artifact_ref("ir", artifact_id)


def _format_validation_errors(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        out.append(f"{loc}: {msg}" if loc else str(msg))
    return out
