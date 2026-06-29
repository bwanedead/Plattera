"""Append-only deed-to-IR final package preview persistence."""

from __future__ import annotations

import json
from typing import Any

from domains.mapping.deed_to_ir.payloads.final_package_preview import (
    DeedToIrFinalPackagePreview,
    LineageSummary,
    MechanicalReviewSummary,
)
from domains.mapping.deed_to_ir.payloads.published_output import (
    DeedToIrOutputSource,
    DeedToIrPublishedOutput,
)
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .final_package_preview_projection import (
    build_preview_hydration_payload,
    build_recommended_publish_request,
    compact_preview_row_summaries,
)
from .final_package_validation import (
    FinalPackageIncompleteError,
    final_package_incomplete_refusal,
    final_package_prepare_validation_refusal,
    validate_prepare_final_package_rows,
)
from .output_package_validation import (
    PublishPayloadValidationError,
    ResolvedMappingPackage,
    resolve_mapping_publish_package,
)
from .persistence_io import (
    atomic_write_json,
    mapping_ir_lineage_mismatch_refusal,
    next_revision_digits,
    read_json,
    refusal,
    resolve_workspace_key,
    rollback_revision_file,
    status_counts,
    utc_now_iso,
    workspace_publish_lock,
)
from .paths import (
    UnsafeDeedToIrPathSegmentError,
    deed_to_ir_preview_latest_pointer_path,
    deed_to_ir_preview_revision_path,
)
from .preview_refs import PREVIEW_REF, build_preview_revision_ref, parse_preview_ref


def prepare_deed_to_ir_final_package(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    mapping_artifact_ref: str,
    scope_results: Any | None = None,
    external_dependencies: Any | None = None,
    closure_dimensions: Any | None = None,
    notes: Any | None = None,
    expected_ir_artifact_ref: str | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
) -> dict[str, Any]:
    if not dossier_id:
        raise ValueError("dossier_id_required")
    if not str(transcription_id or "").strip():
        return refusal("transcription_id_required", "transcription_id is required to prepare final package preview.")
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return refusal(
            "workspace_identity_required",
            "Provide workspace_id or run_id to scope deed-to-IR preview storage.",
        )
    if not str(mapping_artifact_ref or "").strip():
        return refusal("mapping_artifact_ref_required", "mapping_artifact_ref is required.")

    service = persistence or FeatureGraphPersistenceService()
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=service.artifacts_root)
    try:
        package = resolve_mapping_publish_package(
            dossier_id=dossier_id,
            mapping_artifact_ref=str(mapping_artifact_ref).strip(),
            persistence=service,
            sidecars=sidecars,
        )
    except ValueError as exc:
        return refusal(str(exc).strip(), str(exc).strip())

    expected_ir_ref = str(expected_ir_artifact_ref or "").strip()
    actual_ir_ref = str(package.selected_artifacts.ir_artifact_ref or "").strip()
    if expected_ir_ref and actual_ir_ref != expected_ir_ref:
        return mapping_ir_lineage_mismatch_refusal(
            expected_ir_artifact_ref=expected_ir_ref,
            actual_ir_artifact_ref=actual_ir_ref,
        )

    try:
        scopes, deps, closure, note_rows = validate_prepare_final_package_rows(
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
        )
    except PublishPayloadValidationError as exc:
        return final_package_prepare_validation_refusal(
            exc,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
        )
    except FinalPackageIncompleteError as exc:
        return final_package_incomplete_refusal(exc)

    source_ref = str(transcript_edit_source_revision_ref or "").strip()
    if not source_ref:
        return refusal(
            "transcript_edit_source_revision_ref_required",
            "Startup handoff must include transcript_edit source revision ref.",
        )

    lineage_summary = LineageSummary(
        expected_ir_artifact_ref=expected_ir_ref or None,
        current_ir_artifact_ref=actual_ir_ref,
        lineage_mismatch=False,
        mismatch_reason_code=None,
    )
    preview = DeedToIrFinalPackagePreview(
        source=DeedToIrOutputSource(
            transcript_edit_source_revision_ref=source_ref,
            resolution_state_ref=str(resolution_state_ref).strip() if resolution_state_ref else None,
        ),
        selected_artifacts=package.selected_artifacts,
        scope_results=scopes,  # type: ignore[arg-type]
        external_dependencies=deps,  # type: ignore[arg-type]
        closure_dimensions=closure,  # type: ignore[arg-type]
        notes=note_rows,
        mechanical_review_summary=_build_mechanical_review_summary(package),
        lineage_summary=lineage_summary,
        publish_ready_candidate=True,
    )

    revision_digits: str
    revision_ref: str
    try:
        safe_transcription_id = str(transcription_id).strip()
        preview_dir = deed_to_ir_preview_latest_pointer_path(
            dossier_id,
            safe_transcription_id,
            workspace_key,
        ).parent
        with workspace_publish_lock(preview_dir):
            revision_digits = next_revision_digits(revision_dir=preview_dir)
            revision_path = deed_to_ir_preview_revision_path(
                dossier_id,
                safe_transcription_id,
                workspace_key,
                revision_digits,
            )
            if revision_path.exists():
                return refusal("preview_revision_exists", "Preview revision already exists.")
            atomic_write_json(revision_path, preview.model_dump(mode="json"))
            pointer_path = deed_to_ir_preview_latest_pointer_path(
                dossier_id,
                safe_transcription_id,
                workspace_key,
            )
            try:
                atomic_write_json(
                    pointer_path,
                    {
                        "schema_version": "1.0",
                        "revision_digits": revision_digits,
                        "revision_ref": build_preview_revision_ref(revision_digits),
                        "preview_ref": PREVIEW_REF,
                        "prepared_at": utc_now_iso(),
                    },
                )
            except Exception as exc:
                rollback_revision_file(revision_path)
                message = str(exc).strip() or "preview_pointer_write_failed"
                return refusal("preview_pointer_write_failed", message)
            revision_ref = build_preview_revision_ref(revision_digits)
    except UnsafeDeedToIrPathSegmentError as exc:
        return refusal("invalid_scope_path", str(exc))
    except ValueError as exc:
        code = str(exc).strip()
        if code in {"publication_in_progress", "preview_revision_exists"}:
            return refusal(code, code)
        raise

    selected = package.selected_artifacts
    row_summaries = compact_preview_row_summaries(
        scope_results=scopes,
        external_dependencies=deps,
        closure_dimensions=closure,
        notes=note_rows,
    )
    artifact_refs = [
        PREVIEW_REF,
        revision_ref,
        selected.mapping_artifact_ref,
        selected.ir_artifact_ref,
    ]
    return {
        "executed": True,
        "artifact_refs": artifact_refs,
        "outputs": {
            "final_package_preview_ref": PREVIEW_REF,
            "final_package_preview_revision_ref": revision_ref,
            "mapping_artifact_ref": selected.mapping_artifact_ref,
            "ir_artifact_ref": selected.ir_artifact_ref,
            "compile_artifact_ref": selected.compile_artifact_ref,
            "judge_artifact_ref": selected.judge_artifact_ref,
            "geometry_ref": selected.geometry_ref,
            "clean_render_ref": selected.clean_render_ref,
            "control_render_ref": selected.control_render_ref,
            "review_summary": preview.mechanical_review_summary.model_dump(mode="json"),
            "lineage_summary": preview.lineage_summary.model_dump(mode="json"),
            "publish_ready_candidate": True,
            "recommended_publish_request": build_recommended_publish_request(
                preview_revision_ref=revision_ref,
            ),
            **row_summaries,
            "scope_status_counts": status_counts(scopes),
        },
    }


def load_final_package_preview(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision_digits: str | None = None,
) -> dict[str, Any] | None:
    if revision_digits is None:
        pointer = read_json(
            deed_to_ir_preview_latest_pointer_path(dossier_id, transcription_id, workspace_id)
        )
        if pointer is None:
            return None
        revision_digits = str(pointer.get("revision_digits") or "")
    if not revision_digits:
        return None
    return read_json(
        deed_to_ir_preview_revision_path(dossier_id, transcription_id, workspace_id, revision_digits)
    )


def load_final_package_preview_by_ref(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    preview_ref: str,
) -> tuple[dict[str, Any] | None, str | None]:
    kind, revision_digits = parse_preview_ref(preview_ref)
    if kind == "invalid":
        return None, "unsupported_preview_ref"
    if kind == "latest":
        revision_digits = None
    raw = load_final_package_preview(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        revision_digits=revision_digits,
    )
    if raw is None:
        return None, "final_package_preview_not_found"
    return raw, None


def preview_to_published_output(preview: DeedToIrFinalPackagePreview) -> DeedToIrPublishedOutput:
    return DeedToIrPublishedOutput(
        source=preview.source,
        selected_artifacts=preview.selected_artifacts,
        scope_results=preview.scope_results,
        external_dependencies=preview.external_dependencies,
        closure_dimensions=preview.closure_dimensions,
        notes=preview.notes,
    )


def hydrate_final_package_preview_ref(
    *,
    dossier_id: str,
    ref_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    if not str(transcription_id or "").strip():
        return None, "transcription_id_required"
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return None, "workspace_identity_required"

    kind, revision_digits = parse_preview_ref(ref_id)
    if kind == "invalid":
        return None, "unsupported_preview_ref"
    if kind == "latest":
        revision_digits = None

    raw = load_final_package_preview(
        dossier_id=dossier_id,
        transcription_id=str(transcription_id).strip(),
        workspace_id=workspace_key,
        revision_digits=revision_digits,
    )
    if raw is None:
        return None, "final_package_preview_not_found"
    try:
        preview = DeedToIrFinalPackagePreview.model_validate(raw)
    except Exception:
        return None, "final_package_preview_invalid"

    resolved_revision_ref = (
        build_preview_revision_ref(revision_digits)
        if revision_digits
        else _resolve_revision_ref_from_pointer(
            dossier_id=dossier_id,
            transcription_id=str(transcription_id).strip(),
            workspace_id=workspace_key,
        )
    )
    if not resolved_revision_ref:
        resolved_revision_ref = ref_id

    return (
        build_preview_hydration_payload(
            ref_id=ref_id,
            preview=preview.model_dump(mode="json"),
            preview_revision_ref=resolved_revision_ref,
        ),
        None,
    )


def _build_mechanical_review_summary(package: ResolvedMappingPackage) -> MechanicalReviewSummary:
    mapping = package.mapping
    compile_gaps = package.compile_artifact.gaps
    compile_gap_count = len(compile_gaps) if isinstance(compile_gaps, list) else 0
    judge_report = package.judge_artifact.report
    judge_gaps = judge_report.gaps if hasattr(judge_report, "gaps") else []
    judge_finding_count = len(judge_gaps) if isinstance(judge_gaps, list) else 0
    rendered = len(mapping.rendered_feature_ids)
    if rendered <= 0 and isinstance(mapping.geometry.rendered_feature_count, int):
        rendered = mapping.geometry.rendered_feature_count
    skipped = len(mapping.skipped_features)
    if skipped <= 0 and isinstance(mapping.geometry.skipped_feature_count, int):
        skipped = mapping.geometry.skipped_feature_count
    world_bbox = None
    if mapping.world_bbox is not None:
        world_bbox = mapping.world_bbox.model_dump(mode="json")
    return MechanicalReviewSummary(
        compile_gap_count=compile_gap_count,
        judge_finding_count=judge_finding_count,
        rendered_feature_count=rendered,
        skipped_feature_count=skipped,
        coordinate_space=mapping.coordinate_space,
        world_bbox=world_bbox,
    )


def _resolve_revision_ref_from_pointer(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> str | None:
    pointer = read_json(
        deed_to_ir_preview_latest_pointer_path(dossier_id, transcription_id, workspace_id)
    )
    if not isinstance(pointer, dict):
        return None
    revision_ref = pointer.get("revision_ref")
    return str(revision_ref).strip() if revision_ref else None

