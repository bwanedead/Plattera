"""Append-only deed-to-IR published output persistence and publication."""

from __future__ import annotations

from typing import Any

from domains.mapping.deed_to_ir.payloads.final_package_preview import DeedToIrFinalPackagePreview
from domains.mapping.deed_to_ir.payloads.published_output import (
    DeedToIrOutputSource,
    DeedToIrPublishedOutput,
)
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .output_package_validation import (
    PublishPayloadValidationError,
    resolve_mapping_publish_package,
    validate_agent_output_rows,
)
from .output_refs import OUTPUT_REF, build_output_revision_ref
from .paths import (
    UnsafeDeedToIrPathSegmentError,
    deed_to_ir_output_dir,
    deed_to_ir_output_latest_pointer_path,
    deed_to_ir_output_revision_path,
)
from .persistence_io import (
    atomic_write_json,
    final_package_preview_stale_refusal,
    mapping_ir_lineage_mismatch_refusal,
    next_revision_digits,
    read_json,
    refusal,
    resolve_workspace_key,
    rollback_revision_file,
    status_counts,
    utc_now_iso,
    validation_failure_refusal,
    workspace_publish_lock,
)
from .publish_gate_feedback import (
    build_final_output_summary,
    enrich_publish_refusal_result,
)

# Backward-compatible aliases for co-located tests and lazy imports.
_atomic_write_json = atomic_write_json
_read_json = read_json
_refusal = refusal
_mapping_ir_lineage_mismatch_refusal = mapping_ir_lineage_mismatch_refusal
_final_package_preview_stale_refusal = final_package_preview_stale_refusal
_validation_failure_refusal = validation_failure_refusal
_workspace_publish_lock = workspace_publish_lock
_rollback_revision_file = rollback_revision_file
_next_revision_digits = next_revision_digits
_status_counts = status_counts
_utc_now_iso = utc_now_iso


def _publish_refusal(code: str, message: str) -> dict[str, Any]:
    return enrich_publish_refusal_result(_refusal(code, message))


def _enrich_publish_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("executed"):
        return result
    return enrich_publish_refusal_result(result)


def publish_deed_to_ir_output(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    transcript_edit_source_revision_ref: str | None,
    resolution_state_ref: str | None,
    mapping_artifact_ref: str | None = None,
    scope_results: Any | None = None,
    external_dependencies: Any | None = None,
    closure_dimensions: Any | None = None,
    notes: Any | None = None,
    expected_ir_artifact_ref: str | None = None,
    final_package_preview_ref: str | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
) -> dict[str, Any]:
    preview_ref = str(final_package_preview_ref or "").strip()
    mapping_ref = str(mapping_artifact_ref or "").strip()

    if preview_ref and mapping_ref:
        return _publish_refusal(
            "publish_request_ambiguous",
            "Provide either final_package_preview_ref or direct mapping_artifact_ref, not both.",
        )
    if preview_ref:
        row_fields = (
            scope_results,
            external_dependencies,
            closure_dimensions,
            notes,
            expected_ir_artifact_ref,
        )
        if any(field not in (None, [], "") for field in row_fields):
            return _publish_refusal(
                "final_package_preview_row_mutation_forbidden",
                "Publishing from preview uses frozen preview rows; prepare a new preview to change them.",
            )
        return _publish_from_final_package_preview(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
            final_package_preview_ref=preview_ref,
            persistence=persistence,
        )

    if not mapping_ref:
        return _publish_refusal(
            "publish_target_required",
            "Provide final_package_preview_ref (preferred) or mapping_artifact_ref.",
        )

    return _publish_direct(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        transcript_edit_source_revision_ref=transcript_edit_source_revision_ref,
        resolution_state_ref=resolution_state_ref,
        mapping_artifact_ref=mapping_ref,
        scope_results=scope_results,
        external_dependencies=external_dependencies,
        closure_dimensions=closure_dimensions,
        notes=notes,
        expected_ir_artifact_ref=expected_ir_artifact_ref,
        persistence=persistence,
    )


def _publish_direct(
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
        return _publish_refusal("transcription_id_required", "transcription_id is required to publish deed-to-IR output.")
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return _publish_refusal(
            "workspace_identity_required",
            "Provide workspace_id or run_id to scope deed-to-IR output storage.",
        )
    if not str(mapping_artifact_ref or "").strip():
        return _publish_refusal("mapping_artifact_ref_required", "mapping_artifact_ref is required.")

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
        return _publish_refusal(str(exc).strip(), str(exc).strip())

    expected_ir_ref = str(expected_ir_artifact_ref or "").strip()
    if expected_ir_ref:
        actual_ir_ref = str(package.selected_artifacts.ir_artifact_ref or "").strip()
        if actual_ir_ref != expected_ir_ref:
            return _enrich_publish_result(
                _mapping_ir_lineage_mismatch_refusal(
                expected_ir_artifact_ref=expected_ir_ref,
                actual_ir_artifact_ref=actual_ir_ref,
                )
            )

    try:
        scopes, deps, closure, note_rows = validate_agent_output_rows(
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
        )
    except PublishPayloadValidationError as exc:
        return _enrich_publish_result(_validation_failure_refusal(exc))

    source_ref = str(transcript_edit_source_revision_ref or "").strip()
    if not source_ref:
        return _publish_refusal(
            "transcript_edit_source_revision_ref_required",
            "Startup handoff must include transcript_edit source revision ref.",
        )

    published = DeedToIrPublishedOutput(
        source=DeedToIrOutputSource(
            transcript_edit_source_revision_ref=source_ref,
            resolution_state_ref=str(resolution_state_ref).strip() if resolution_state_ref else None,
        ),
        selected_artifacts=package.selected_artifacts,
        scope_results=scopes,  # type: ignore[arg-type]
        external_dependencies=deps,  # type: ignore[arg-type]
        closure_dimensions=closure,  # type: ignore[arg-type]
        notes=note_rows,
    )
    return _persist_published_output(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        published=published,
        package=package,
        persistence=service,
    )


def _publish_from_final_package_preview(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    final_package_preview_ref: str,
    persistence: FeatureGraphPersistenceService | None = None,
) -> dict[str, Any]:
    from .final_package_preview_persistence import load_final_package_preview_by_ref, preview_to_published_output

    if not dossier_id:
        raise ValueError("dossier_id_required")
    if not str(transcription_id or "").strip():
        return _publish_refusal("transcription_id_required", "transcription_id is required to publish deed-to-IR output.")
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return _publish_refusal(
            "workspace_identity_required",
            "Provide workspace_id or run_id to scope deed-to-IR output storage.",
        )

    raw, error = load_final_package_preview_by_ref(
        dossier_id=dossier_id,
        transcription_id=str(transcription_id).strip(),
        workspace_id=workspace_key,
        preview_ref=final_package_preview_ref,
    )
    if raw is None:
        return _publish_refusal(error or "final_package_preview_not_found", error or "final_package_preview_not_found")

    try:
        preview = DeedToIrFinalPackagePreview.model_validate(raw)
    except Exception:
        return _publish_refusal("final_package_preview_invalid", "Stored final package preview is invalid.")

    if not preview.publish_ready_candidate:
        return _publish_refusal(
            "final_package_preview_not_ready",
            "Preview was not marked publish_ready_candidate; prepare a new preview.",
        )

    service = persistence or FeatureGraphPersistenceService()
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=service.artifacts_root)
    mapping_ref = preview.selected_artifacts.mapping_artifact_ref
    try:
        package = resolve_mapping_publish_package(
            dossier_id=dossier_id,
            mapping_artifact_ref=mapping_ref,
            persistence=service,
            sidecars=sidecars,
        )
    except ValueError as exc:
        return _publish_refusal(str(exc).strip(), str(exc).strip())

    preview_ir = str(preview.selected_artifacts.ir_artifact_ref or "").strip()
    current_ir = str(package.selected_artifacts.ir_artifact_ref or "").strip()
    if preview_ir != current_ir:
        return _enrich_publish_result(
            _final_package_preview_stale_refusal(
            preview_ir_artifact_ref=preview_ir,
            current_ir_artifact_ref=current_ir,
            )
        )

    expected_ir = str(preview.lineage_summary.expected_ir_artifact_ref or "").strip()
    if expected_ir and current_ir != expected_ir:
        return _enrich_publish_result(
            _mapping_ir_lineage_mismatch_refusal(
            expected_ir_artifact_ref=expected_ir,
            actual_ir_artifact_ref=current_ir,
            )
        )

    published = preview_to_published_output(preview)
    return _persist_published_output(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        published=published,
        package=package,
        persistence=service,
        final_package_preview_ref=final_package_preview_ref,
    )


def _persist_published_output(
    *,
    dossier_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
    published: DeedToIrPublishedOutput,
    package: Any,
    persistence: FeatureGraphPersistenceService,
    final_package_preview_ref: str | None = None,
) -> dict[str, Any]:
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return _publish_refusal(
            "workspace_identity_required",
            "Provide workspace_id or run_id to scope deed-to-IR output storage.",
        )

    revision_digits: str
    revision_ref: str
    try:
        safe_transcription_id = str(transcription_id).strip()
        output_dir = deed_to_ir_output_dir(dossier_id, safe_transcription_id, workspace_key)
        with _workspace_publish_lock(output_dir):
            revision_digits = _next_revision_digits(revision_dir=output_dir)
            revision_path = deed_to_ir_output_revision_path(
                dossier_id,
                safe_transcription_id,
                workspace_key,
                revision_digits,
            )
            if revision_path.exists():
                return _publish_refusal("output_revision_exists", "Output revision already exists.")
            _atomic_write_json(revision_path, published.model_dump(mode="json"))

            try:
                persistence.mark_final_artifacts(
                    dossier_id=dossier_id,
                    targets={
                        "ir": package.ir_artifact.artifact_id,
                        "mapping": package.mapping.artifact_id,
                    },
                )
            except Exception as exc:
                _rollback_revision_file(revision_path)
                message = str(exc).strip() or "final_pointer_write_failed"
                return _publish_refusal("final_pointer_write_failed", message)

            pointer_path = deed_to_ir_output_latest_pointer_path(
                dossier_id,
                safe_transcription_id,
                workspace_key,
            )
            _atomic_write_json(
                pointer_path,
                {
                    "schema_version": "1.0",
                    "revision_digits": revision_digits,
                    "revision_ref": build_output_revision_ref(revision_digits),
                    "output_ref": OUTPUT_REF,
                    "published_at": _utc_now_iso(),
                },
            )
            revision_ref = build_output_revision_ref(revision_digits)
    except UnsafeDeedToIrPathSegmentError as exc:
        return _publish_refusal("invalid_scope_path", str(exc))
    except ValueError as exc:
        code = str(exc).strip()
        if code in {"publication_in_progress", "output_revision_exists"}:
            return _publish_refusal(code, code)
        raise

    selected = package.selected_artifacts
    scopes = [row.model_dump(mode="json") for row in published.scope_results]
    deps = [row.model_dump(mode="json") for row in published.external_dependencies]
    closure = [row.model_dump(mode="json") for row in published.closure_dimensions]
    note_rows = [row.model_dump(mode="json") for row in published.notes]
    artifact_refs = [
        OUTPUT_REF,
        revision_ref,
        selected.mapping_artifact_ref,
        selected.control_render_ref,
        selected.clean_render_ref,
        selected.geometry_ref,
        selected.compile_artifact_ref,
        selected.judge_artifact_ref,
        selected.ir_artifact_ref,
    ]
    scope_status_counts = _status_counts(scopes)
    closure_dimension_statuses = [
        {"dimension_id": row["dimension_id"], "status": row["status"]}
        for row in closure
    ]
    preview_ref = str(final_package_preview_ref or "").strip() or None
    outputs: dict[str, Any] = {
        "output_ref": OUTPUT_REF,
        "output_revision_ref": revision_ref,
        "mapping_artifact_ref": selected.mapping_artifact_ref,
        "ir_artifact_ref": selected.ir_artifact_ref,
        "compile_artifact_ref": selected.compile_artifact_ref,
        "judge_artifact_ref": selected.judge_artifact_ref,
        "geometry_ref": selected.geometry_ref,
        "clean_render_ref": selected.clean_render_ref,
        "control_render_ref": selected.control_render_ref,
        "scope_result_count": len(scopes),
        "scope_status_counts": scope_status_counts,
        "external_dependency_count": len(deps),
        "closure_dimension_count": len(closure),
        "closure_dimension_statuses": closure_dimension_statuses,
        "note_count": len(note_rows),
        "final_output_summary": build_final_output_summary(publish_succeeded=True),
    }
    if preview_ref:
        outputs["final_package_preview_ref"] = preview_ref
    return {
        "executed": True,
        "artifact_refs": artifact_refs,
        "outputs": outputs,
    }


def load_published_output(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision_digits: str | None = None,
) -> dict[str, Any] | None:
    if revision_digits is None:
        pointer = _read_json(
            deed_to_ir_output_latest_pointer_path(dossier_id, transcription_id, workspace_id)
        )
        if pointer is None:
            return None
        revision_digits = str(pointer.get("revision_digits") or "")
    if not revision_digits:
        return None
    return _read_json(
        deed_to_ir_output_revision_path(dossier_id, transcription_id, workspace_id, revision_digits)
    )


# Shared helpers live in persistence_io.py; aliases above preserve test imports.
