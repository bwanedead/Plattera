"""Append-only deed-to-IR final package preview persistence."""

from __future__ import annotations

import json
from collections.abc import Mapping
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

from .correction_lane_advisory import detect_correction_lane_advisory
from .correction_posture import (
    detect_correction_posture,
    upstream_corrections_required_refusal,
)
from .final_package_preview_projection import (
    build_preview_hydration_payload,
    build_recommended_publish_request,
    compact_preview_row_summaries,
    enrich_prepare_preview_tool_outputs,
)
from .final_package_validation import (
    FinalPackageIncompleteError,
    final_package_incomplete_refusal,
    final_package_prepare_combined_refusal,
    final_package_prepare_validation_refusal,
    validate_prepare_final_package_rows,
)
from .final_package_retry_projection import build_retry_package_shell
from .dependency_candidates_projection import (
    compact_dependency_candidate_diagnostics_for_projection,
    project_known_dependency_candidates,
)
from .dependency_decisions import resolve_intent_first_external_dependencies
from .intent_first_preflight import evaluate_intent_first_decision_preflight
from .intent_first_prepare import (
    assemble_upstream_corrections_from_decisions,
    build_intent_first_correction_summary,
    expand_compact_dispositions,
    extract_agent_authored_finalization_state,
)
from .mapping_lineage import (
    compact_current_mapping_lineage_for_projection,
    resolve_intent_first_mapping_lineage,
)
from .output_package_validation import (
    PublishPayloadValidationError,
    ResolvedMappingPackage,
    mapping_artifact_not_found_refusal,
    resolve_mapping_publish_package,
    validate_upstream_correction_rows_only,
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
    mapping_artifact_ref: str | None = None,
    scope_results: Any | None = None,
    external_dependencies: Any | None = None,
    closure_dimensions: Any | None = None,
    notes: Any | None = None,
    upstream_corrections: Any | None = None,
    expected_ir_artifact_ref: str | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
    use_current_mapping_lineage: bool = False,
    reuse_agent_authored_finalization_state: bool = False,
    correction_decisions: Any | None = None,
    scope_dispositions: Any | None = None,
    closure_dispositions: Any | None = None,
    dependency_decisions: Any | None = None,
    issues: Any | None = None,
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

    intent_first = bool(use_current_mapping_lineage)
    resolved_mapping_ref = str(mapping_artifact_ref or "").strip()
    resolved_expected_ir = str(expected_ir_artifact_ref or "").strip()
    current_lineage_compact: dict[str, Any] | None = None
    dependency_candidate_diagnostics: list[dict[str, Any]] = []

    if intent_first:
        lineage_resolution = resolve_intent_first_mapping_lineage(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )
        if lineage_resolution.get("executed") is not True:
            return lineage_resolution
        resolved_mapping_ref = str(lineage_resolution["mapping_artifact_ref"]).strip()
        resolved_expected_ir = str(lineage_resolution["expected_ir_artifact_ref"]).strip()
        current_lineage_compact = compact_current_mapping_lineage_for_projection(
            lineage_resolution.get("current_mapping_lineage")
            if isinstance(lineage_resolution.get("current_mapping_lineage"), Mapping)
            else None
        )

        # Optional reuse of prior agent-authored rows (not a substitute for preflight).
        has_compact = isinstance(scope_dispositions, list) or isinstance(
            closure_dispositions, list
        )
        if (
            scope_results is None
            and closure_dimensions is None
            and not has_compact
            and reuse_agent_authored_finalization_state
        ):
            prior = load_final_package_preview(
                dossier_id=dossier_id,
                transcription_id=str(transcription_id).strip(),
                workspace_id=workspace_key,
            )
            reused = extract_agent_authored_finalization_state(prior)
            if reused is not None:
                if scope_results is None:
                    scope_results = reused["scope_results"]
                if external_dependencies is None:
                    external_dependencies = reused["external_dependencies"]
                if closure_dimensions is None:
                    closure_dimensions = reused["closure_dimensions"]
                if notes is None:
                    notes = reused["notes"]
    elif not resolved_mapping_ref:
        return refusal("mapping_artifact_ref_required", "mapping_artifact_ref is required.")

    upstream_validation_exc: PublishPayloadValidationError | None = None
    if upstream_corrections is not None:
        try:
            validate_upstream_correction_rows_only(upstream_corrections)
        except PublishPayloadValidationError as exc:
            upstream_validation_exc = exc

    service = persistence or FeatureGraphPersistenceService()
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=service.artifacts_root)
    try:
        package = resolve_mapping_publish_package(
            dossier_id=dossier_id,
            mapping_artifact_ref=resolved_mapping_ref,
            persistence=service,
            sidecars=sidecars,
        )
    except ValueError as exc:
        code = str(exc).strip()
        if code == "mapping_artifact_not_found":
            return mapping_artifact_not_found_refusal(
                persistence=service,
                dossier_id=dossier_id,
                requested_ref=resolved_mapping_ref,
            )
        return refusal(code, code)

    expected_ir_ref = resolved_expected_ir
    actual_ir_ref = str(package.selected_artifacts.ir_artifact_ref or "").strip()
    lineage_mismatch = bool(expected_ir_ref and actual_ir_ref != expected_ir_ref)
    if upstream_validation_exc is not None and lineage_mismatch:
        return final_package_prepare_combined_refusal(
            validation_exc=upstream_validation_exc,
            expected_ir_artifact_ref=expected_ir_ref,
            actual_ir_artifact_ref=actual_ir_ref,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        )
    if upstream_validation_exc is not None:
        return final_package_prepare_validation_refusal(
            upstream_validation_exc,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        )
    if lineage_mismatch:
        return mapping_ir_lineage_mismatch_refusal(
            expected_ir_artifact_ref=expected_ir_ref,
            actual_ir_artifact_ref=actual_ir_ref,
        )

    if intent_first:
        correction_posture_early = detect_correction_posture(
            resolution_state_snapshot=resolution_state_snapshot,
            ir_graph=package.ir_artifact.graph,
            compile_artifact=package.compile_artifact,
            ir_artifact_ref=actual_ir_ref,
        )
        projected = project_known_dependency_candidates(
            resolution_state_snapshot=resolution_state_snapshot,
            issues=issues if isinstance(issues, list) else None,
            resolution_state_ref=resolution_state_ref,
        )
        known_candidates = list(projected.get("candidates") or [])
        candidate_diagnostics = list(projected.get("diagnostics") or [])

        preflight = evaluate_intent_first_decision_preflight(
            scope_dispositions=scope_dispositions,
            closure_dispositions=closure_dispositions,
            correction_decisions=correction_decisions,
            dependency_decisions=dependency_decisions,
            scope_results=scope_results,
            closure_dimensions=closure_dimensions,
            external_dependencies=external_dependencies,
            upstream_corrections=upstream_corrections,
            correction_posture=correction_posture_early,
            known_dependency_candidates=known_candidates,
        )
        if preflight.get("complete") is not True:
            return preflight

        # Strict expansion only after all required lanes are present.
        has_compact = isinstance(scope_dispositions, list) or isinstance(
            closure_dispositions, list
        )
        if scope_results is None and closure_dimensions is None and has_compact:
            expanded = expand_compact_dispositions(
                scope_dispositions=scope_dispositions
                if isinstance(scope_dispositions, list)
                else None,
                closure_dispositions=closure_dispositions
                if isinstance(closure_dispositions, list)
                else None,
                mapping_artifact_ref=resolved_mapping_ref,
                ir_artifact_ref=resolved_expected_ir,
            )
            if expanded.get("executed") is not True:
                return expanded
            scope_results = expanded["scope_results"]
            closure_dimensions = expanded["closure_dimensions"]

        resolved_deps = resolve_intent_first_external_dependencies(
            known_candidates=known_candidates,
            external_dependencies=external_dependencies
            if isinstance(external_dependencies, list)
            else None,
            dependency_decisions=dependency_decisions
            if isinstance(dependency_decisions, list)
            else None,
            diagnostics=candidate_diagnostics,
        )
        if resolved_deps.get("executed") is not True:
            return resolved_deps
        external_dependencies = list(resolved_deps.get("rows") or [])
        dependency_candidate_diagnostics = compact_dependency_candidate_diagnostics_for_projection(
            resolved_deps.get("diagnostics")
            if isinstance(resolved_deps.get("diagnostics"), list)
            else candidate_diagnostics
        )

        if upstream_corrections is None:
            assembled = assemble_upstream_corrections_from_decisions(
                correction_decisions=correction_decisions
                if isinstance(correction_decisions, list)
                else None,
                correction_posture=correction_posture_early,
                mapping_artifact_ref=resolved_mapping_ref,
                ir_artifact_ref=actual_ir_ref,
            )
            if assembled.get("executed") is not True:
                return assembled
            upstream_corrections = list(assembled.get("rows") or [])

    try:
        scopes, deps, closure, note_rows, corrections = validate_prepare_final_package_rows(
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        )
    except PublishPayloadValidationError as exc:
        return final_package_prepare_validation_refusal(
            exc,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        )
    except FinalPackageIncompleteError as exc:
        return final_package_incomplete_refusal(exc)

    correction_posture = detect_correction_posture(
        resolution_state_snapshot=resolution_state_snapshot,
        ir_graph=package.ir_artifact.graph,
        compile_artifact=package.compile_artifact,
        ir_artifact_ref=actual_ir_ref,
        upstream_corrections=corrections,
        scope_results=scopes,
        external_dependencies=deps,
        closure_dimensions=closure,
        notes=note_rows,
    )
    if correction_posture.get("active") and not corrections:
        if intent_first:
            # Intent-first already assembled above; empty corrections means decisions were missing.
            return assemble_upstream_corrections_from_decisions(
                correction_decisions=correction_decisions if isinstance(correction_decisions, list) else [],
                correction_posture=correction_posture,
                mapping_artifact_ref=resolved_mapping_ref,
                ir_artifact_ref=actual_ir_ref,
            )
        retry_shell = build_retry_package_shell(
            mapping_artifact_ref=resolved_mapping_ref,
            expected_ir_artifact_ref=actual_ir_ref,
            scope_results=scopes,
            external_dependencies=deps,
            closure_dimensions=closure,
            notes=note_rows,
            correction_posture=correction_posture,
        )
        return upstream_corrections_required_refusal(
            correction_posture=correction_posture,
            retry_package_shell=retry_shell,
        )

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
    correction_lane_advisory = detect_correction_lane_advisory(
        upstream_corrections=corrections,
        scope_results=scopes,
        external_dependencies=deps,
        closure_dimensions=closure,
        notes=note_rows,
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
        upstream_corrections=corrections,  # type: ignore[arg-type]
        mechanical_review_summary=_build_mechanical_review_summary(package),
        lineage_summary=lineage_summary,
        publish_ready_candidate=True,
        correction_lane_advisory=correction_lane_advisory,
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
        upstream_corrections=corrections,
    )
    artifact_refs = [
        PREVIEW_REF,
        revision_ref,
        selected.mapping_artifact_ref,
        selected.ir_artifact_ref,
    ]
    base_outputs: dict[str, Any] = {
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
        **row_summaries,
        "scope_status_counts": status_counts(scopes),
        **(
            {"correction_lane_advisory": correction_lane_advisory}
            if correction_lane_advisory is not None
            else {}
        ),
    }
    if intent_first:
        base_outputs["finalization_status"] = "preview_ready"
        base_outputs["selected_lineage"] = {
            "mapping_artifact_ref": selected.mapping_artifact_ref,
            "expected_ir_artifact_ref": actual_ir_ref,
        }
        base_outputs["correction_summary"] = build_intent_first_correction_summary(
            rows=corrections,
            correction_posture=correction_posture,
        )
        if current_lineage_compact is not None:
            base_outputs["current_mapping_lineage"] = current_lineage_compact
        if dependency_candidate_diagnostics:
            base_outputs["dependency_candidate_diagnostics"] = dependency_candidate_diagnostics
    return {
        "executed": True,
        "artifact_refs": artifact_refs,
        "outputs": enrich_prepare_preview_tool_outputs(
            base_outputs,
            preview_revision_ref=revision_ref,
            preview_ref=PREVIEW_REF,
        ),
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
        upstream_corrections=preview.upstream_corrections,
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

