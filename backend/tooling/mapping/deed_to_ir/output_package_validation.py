"""Mechanical mapping-package validation for deed-to-IR publication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import (
    ALLOWED_CLOSURE_DIMENSION_IDS,
    MAX_CLOSURE_DIMENSIONS,
    MAX_EXTERNAL_DEPENDENCIES,
    MAX_NOTES,
    MAX_SCOPE_RESULTS,
    ClosureDimensionRow,
    DeedToIrSelectedArtifacts,
    ExternalDependencyRow,
    ScopeResultRow,
)
from feature_graph.artifact_refs import parse_feature_graph_artifact_ref
from feature_graph.artifacts import CompileArtifact, IRArtifact, JudgeArtifact
from feature_graph.mapping_artifacts import MappingArtifact
from pydantic import ValidationError
from services.feature_graph.feature_graph_mapping_service import require_exact_ir_parent
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


@dataclass(frozen=True)
class ResolvedMappingPackage:
    mapping: MappingArtifact
    ir_artifact: IRArtifact
    compile_artifact: CompileArtifact
    judge_artifact: JudgeArtifact
    selected_artifacts: DeedToIrSelectedArtifacts


def resolve_mapping_publish_package(
    *,
    dossier_id: str,
    mapping_artifact_ref: str,
    persistence: FeatureGraphPersistenceService,
    sidecars: FeatureGraphMappingSidecarService | None = None,
) -> ResolvedMappingPackage:
    parsed = _parse_mapping_ref(mapping_artifact_ref)
    if parsed is None:
        raise ValueError("mapping_artifact_ref_invalid")
    _, mapping_id = parsed
    raw = persistence.get_artifact(dossier_id, mapping_id)
    if not isinstance(raw, dict):
        raise ValueError("mapping_artifact_not_found")
    if str(raw.get("artifact_type") or "") != "mapping":
        raise ValueError("mapping_artifact_type_mismatch")
    try:
        mapping = MappingArtifact.model_validate(raw)
    except Exception as exc:
        raise ValueError("mapping_artifact_invalid") from exc

    ir_raw = persistence.get_artifact(dossier_id, mapping.source_ir_artifact_id)
    compile_raw = persistence.get_artifact(dossier_id, mapping.compile_artifact_id)
    judge_raw = persistence.get_artifact(dossier_id, mapping.judge_artifact_id)
    if not isinstance(ir_raw, dict):
        raise ValueError("ir_artifact_not_found")
    if not isinstance(compile_raw, dict):
        raise ValueError("compile_artifact_not_found")
    if not isinstance(judge_raw, dict):
        raise ValueError("judge_artifact_not_found")

    _require_exact_artifact_type(ir_raw, expected="ir", code="ir_artifact_type_mismatch")
    _require_exact_artifact_type(compile_raw, expected="compile", code="compile_artifact_type_mismatch")
    _require_exact_artifact_type(judge_raw, expected="judge", code="judge_artifact_type_mismatch")

    try:
        ir_artifact = IRArtifact.model_validate(ir_raw)
        compile_artifact = CompileArtifact.model_validate(compile_raw)
        judge_artifact = JudgeArtifact.model_validate(judge_raw)
    except Exception as exc:
        raise ValueError("lineage_artifact_invalid") from exc

    graph_id = mapping.graph_id
    if ir_artifact.graph.graph_id != graph_id:
        raise ValueError("ir_graph_id_mismatch")
    if compile_artifact.graph_id != graph_id:
        raise ValueError("compile_graph_id_mismatch")
    if judge_artifact.graph_id != graph_id:
        raise ValueError("judge_graph_id_mismatch")
    if judge_artifact.report.graph_id != graph_id:
        raise ValueError("judge_report_graph_id_mismatch")

    if mapping.source_ir_artifact_ref != build_ref("ir", mapping.source_ir_artifact_id):
        raise ValueError("mapping_ir_ref_mismatch")
    if mapping.compile_artifact_ref != build_ref("compile", mapping.compile_artifact_id):
        raise ValueError("mapping_compile_ref_mismatch")
    if mapping.judge_artifact_ref != build_ref("judge", mapping.judge_artifact_id):
        raise ValueError("mapping_judge_ref_mismatch")

    require_exact_ir_parent(
        artifact=compile_artifact,
        ir_artifact_id=ir_artifact.artifact_id,
        role="compile",
    )
    require_exact_ir_parent(
        artifact=judge_artifact,
        ir_artifact_id=ir_artifact.artifact_id,
        role="judge",
    )
    parents = [str(item) for item in (mapping.metadata.parent_artifact_ids or [])]
    for artifact_id in (
        ir_artifact.artifact_id,
        compile_artifact.artifact_id,
        judge_artifact.artifact_id,
    ):
        if artifact_id not in parents:
            raise ValueError("mapping_lineage_mismatch")

    sidecar_service = sidecars or FeatureGraphMappingSidecarService(artifacts_root=persistence.artifacts_root)
    _verify_sidecar(sidecar_service, dossier_id, mapping.artifact_id, mapping.geometry.ref, "geometry.geojson")
    _verify_sidecar(sidecar_service, dossier_id, mapping.artifact_id, mapping.clean_render.ref, "clean.png")
    _verify_sidecar(sidecar_service, dossier_id, mapping.artifact_id, mapping.control_render.ref, "control.png")

    selected = DeedToIrSelectedArtifacts(
        ir_artifact_ref=mapping.source_ir_artifact_ref,
        compile_artifact_ref=mapping.compile_artifact_ref,
        judge_artifact_ref=mapping.judge_artifact_ref,
        mapping_artifact_ref=mapping_artifact_ref.strip(),
        geometry_ref=mapping.geometry.ref,
        clean_render_ref=mapping.clean_render.ref,
        control_render_ref=mapping.control_render.ref,
    )
    return ResolvedMappingPackage(
        mapping=mapping,
        ir_artifact=ir_artifact,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
        selected_artifacts=selected,
    )


def build_ref(artifact_type: str, artifact_id: str) -> str:
    from feature_graph.artifact_refs import build_feature_graph_artifact_ref

    return build_feature_graph_artifact_ref(artifact_type, artifact_id)  # type: ignore[arg-type]


def _parse_mapping_ref(ref: str) -> tuple[str, str] | None:
    try:
        artifact_type, artifact_id = parse_feature_graph_artifact_ref(ref)
    except ValueError:
        return None
    if artifact_type != "mapping":
        return None
    return artifact_type, artifact_id


def _require_exact_artifact_type(raw: dict[str, Any], *, expected: str, code: str) -> None:
    if str(raw.get("artifact_type") or "") != expected:
        raise ValueError(code)


def _verify_sidecar(
    sidecars: FeatureGraphMappingSidecarService,
    dossier_id: str,
    mapping_id: str,
    ref: str,
    sidecar_name: str,
) -> None:
    expected = sidecars.build_sidecar_ref(dossier_id, mapping_id, sidecar_name)  # type: ignore[arg-type]
    if ref != expected:
        raise ValueError("mapping_sidecar_ref_mismatch")
    try:
        sidecars.resolve_existing_sidecar_path(dossier_id, mapping_id, sidecar_name)  # type: ignore[arg-type]
    except Exception as exc:
        raise ValueError("mapping_sidecar_missing") from exc


def validate_agent_output_rows(
    *,
    scope_results: list[Any],
    external_dependencies: list[Any],
    closure_dimensions: list[Any],
    notes: list[Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    if len(scope_results) > MAX_SCOPE_RESULTS:
        raise ValueError("scope_results_cap_exceeded")
    if len(external_dependencies) > MAX_EXTERNAL_DEPENDENCIES:
        raise ValueError("external_dependencies_cap_exceeded")
    if len(closure_dimensions) > MAX_CLOSURE_DIMENSIONS:
        raise ValueError("closure_dimensions_cap_exceeded")
    if len(notes) > MAX_NOTES:
        raise ValueError("notes_cap_exceeded")

    validated_scopes = [
        _validate_row(ScopeResultRow, row, code_prefix="scope_results").model_dump(mode="json")
        for row in scope_results
    ]
    validated_deps = [
        _validate_row(ExternalDependencyRow, row, code_prefix="external_dependencies").model_dump(mode="json")
        for row in external_dependencies
    ]
    validated_closure = [
        _validate_row(ClosureDimensionRow, row, code_prefix="closure_dimensions").model_dump(mode="json")
        for row in closure_dimensions
    ]
    validated_notes = [_validate_note(note) for note in notes]

    _assert_unique([row["scope_id"] for row in validated_scopes], code="scope_id_not_unique")
    _assert_unique([row["dependency_id"] for row in validated_deps], code="dependency_id_not_unique")
    closure_ids = [row["dimension_id"] for row in validated_closure]
    _assert_unique(closure_ids, code="closure_dimension_id_not_unique")
    for dimension_id in closure_ids:
        if dimension_id not in ALLOWED_CLOSURE_DIMENSION_IDS:
            raise ValueError("closure_dimension_id_invalid")

    return validated_scopes, validated_deps, validated_closure, validated_notes


def _validate_row(model_cls: type, row: Any, *, code_prefix: str):
    if not isinstance(row, dict):
        raise ValueError(f"{code_prefix}_invalid")
    try:
        return model_cls.model_validate(row)
    except ValidationError as exc:
        raise ValueError(_validation_reason_code(exc, code_prefix)) from exc


def _validate_note(note: Any) -> str:
    if not isinstance(note, str):
        raise ValueError("notes_invalid")
    text = note.strip()
    if not text:
        raise ValueError("notes_invalid")
    try:
        from domains.mapping.deed_to_ir.payloads.published_output import MAX_NOTE_LENGTH

        if len(text) > MAX_NOTE_LENGTH:
            raise ValueError("note_too_long")
    except ValueError:
        raise
    return text


def _assert_unique(values: list[str], *, code: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(code)


def _validation_reason_code(exc: ValidationError, prefix: str) -> str:
    for err in exc.errors():
        err_type = str(err.get("type") or "")
        loc = err.get("loc") or ()
        if err_type == "extra_forbidden":
            return f"{prefix}_extra_field"
        if err_type in {"too_long", "string_too_long"}:
            return f"{prefix}_too_long"
        if err_type in {"too_short", "string_too_short", "missing"}:
            return f"{prefix}_invalid"
        if err_type == "value_error":
            ctx = err.get("ctx") or {}
            if isinstance(ctx.get("error"), Exception):
                message = str(ctx["error"])
            else:
                message = str(err.get("msg") or "")
            if "blank" in message:
                return f"{prefix}_blank_field"
            if "ref_too_long" in message:
                return f"{prefix}_ref_too_long"
            if "not_unique" in message or "invalid" in message:
                mapped = message.replace("Value error, ", "").strip()
                if mapped in {
                    "scope_id_not_unique",
                    "dependency_id_not_unique",
                    "closure_dimension_id_not_unique",
                    "closure_dimension_id_invalid",
                    "blank_note",
                    "note_too_long",
                }:
                    return mapped
            return f"{prefix}_invalid"
        if loc:
            return f"{prefix}_invalid"
    return f"{prefix}_invalid"
