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
    MAX_UPSTREAM_CORRECTIONS,
    ClosureDimensionRow,
    DeedToIrSelectedArtifacts,
    ExternalDependencyRow,
    OutputNoteRow,
    ScopeResultRow,
    UpstreamCorrectionRow,
)
from feature_graph.artifact_refs import parse_feature_graph_artifact_ref
from feature_graph.artifacts import CompileArtifact, IRArtifact, JudgeArtifact
from feature_graph.mapping_artifacts import MappingArtifact
from pydantic import ValidationError
from services.feature_graph.feature_graph_mapping_service import require_exact_ir_parent
from services.feature_graph.feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

MAX_PUBLISH_VALIDATION_ERRORS = 24
PUBLISH_PAYLOAD_VALIDATION_FAILED = "publish_payload_validation_failed"


class PublishPayloadValidationError(Exception):
    """Retryable publish payload validation failure with bounded field feedback."""

    def __init__(
        self,
        validation_errors: tuple[dict[str, str], ...] | list[dict[str, str]],
        *,
        reason_code: str = PUBLISH_PAYLOAD_VALIDATION_FAILED,
        prepare_repair_packet: dict[str, Any] | None = None,
    ) -> None:
        self.validation_errors = tuple(validation_errors)
        self.reason_code = reason_code
        self.prepare_repair_packet = prepare_repair_packet
        super().__init__(reason_code)


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
    scope_results: Any = None,
    external_dependencies: Any = None,
    closure_dimensions: Any = None,
    notes: Any = None,
    upstream_corrections: Any = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    errors: list[dict[str, str]] = []

    scope_list, scope_type_errors = _require_row_list(scope_results, field_name="scope_results")
    errors.extend(scope_type_errors)
    dep_list, dep_type_errors = _require_row_list(external_dependencies, field_name="external_dependencies")
    errors.extend(dep_type_errors)
    closure_list, closure_type_errors = _require_row_list(closure_dimensions, field_name="closure_dimensions")
    errors.extend(closure_type_errors)
    note_list, note_type_errors = _require_row_list(notes, field_name="notes")
    errors.extend(note_type_errors)
    correction_list, correction_type_errors = _require_row_list(
        upstream_corrections,
        field_name="upstream_corrections",
    )
    errors.extend(correction_type_errors)

    if len(scope_list) > MAX_SCOPE_RESULTS:
        errors.append(
            _cap_error(
                path="scope_results",
                code="cap_exceeded",
                message=f"scope_results exceeds maximum of {MAX_SCOPE_RESULTS} items",
            )
        )
    if len(dep_list) > MAX_EXTERNAL_DEPENDENCIES:
        errors.append(
            _cap_error(
                path="external_dependencies",
                code="cap_exceeded",
                message=f"external_dependencies exceeds maximum of {MAX_EXTERNAL_DEPENDENCIES} items",
            )
        )
    if len(closure_list) > MAX_CLOSURE_DIMENSIONS:
        errors.append(
            _cap_error(
                path="closure_dimensions",
                code="cap_exceeded",
                message=f"closure_dimensions exceeds maximum of {MAX_CLOSURE_DIMENSIONS} items",
            )
        )
    if len(note_list) > MAX_NOTES:
        errors.append(
            _cap_error(
                path="notes",
                code="cap_exceeded",
                message=f"notes exceeds maximum of {MAX_NOTES} items",
            )
        )
    if len(correction_list) > MAX_UPSTREAM_CORRECTIONS:
        errors.append(
            _cap_error(
                path="upstream_corrections",
                code="cap_exceeded",
                message=f"upstream_corrections exceeds maximum of {MAX_UPSTREAM_CORRECTIONS} items",
            )
        )

    validated_scopes: list[dict[str, Any]] = []
    for index, row in enumerate(scope_list):
        validated, row_errors = _validate_row_at(
            ScopeResultRow,
            row,
            path_prefix=f"scope_results[{index}]",
        )
        if validated is not None:
            validated_scopes.append(validated)
        errors.extend(row_errors)

    validated_deps: list[dict[str, Any]] = []
    for index, row in enumerate(dep_list):
        validated, row_errors = _validate_row_at(
            ExternalDependencyRow,
            row,
            path_prefix=f"external_dependencies[{index}]",
        )
        if validated is not None:
            validated_deps.append(validated)
        errors.extend(row_errors)

    validated_closure: list[dict[str, Any]] = []
    for index, row in enumerate(closure_list):
        validated, row_errors = _validate_row_at(
            ClosureDimensionRow,
            row,
            path_prefix=f"closure_dimensions[{index}]",
        )
        if validated is not None:
            validated_closure.append(validated)
        errors.extend(row_errors)

    validated_notes: list[dict[str, Any]] = []
    for index, row in enumerate(note_list):
        validated, row_errors = _validate_row_at(
            OutputNoteRow,
            row,
            path_prefix=f"notes[{index}]",
        )
        if validated is not None:
            validated_notes.append(validated)
        errors.extend(row_errors)

    validated_corrections: list[dict[str, Any]] = []
    for index, row in enumerate(correction_list):
        validated, row_errors = _validate_row_at(
            UpstreamCorrectionRow,
            row,
            path_prefix=f"upstream_corrections[{index}]",
        )
        if validated is not None:
            validated_corrections.append(validated)
        errors.extend(row_errors)

    _collect_uniqueness_errors(
        [row["scope_id"] for row in validated_scopes],
        path="scope_results",
        code="scope_id_not_unique",
        errors=errors,
    )
    _collect_uniqueness_errors(
        [row["dependency_id"] for row in validated_deps],
        path="external_dependencies",
        code="dependency_id_not_unique",
        errors=errors,
    )
    _collect_uniqueness_errors(
        [row["dimension_id"] for row in validated_closure],
        path="closure_dimensions",
        code="closure_dimension_id_not_unique",
        errors=errors,
    )
    _collect_uniqueness_errors(
        [row["note_id"] for row in validated_notes],
        path="notes",
        code="note_id_not_unique",
        errors=errors,
    )
    _collect_uniqueness_errors(
        [row["correction_id"] for row in validated_corrections],
        path="upstream_corrections",
        code="correction_id_not_unique",
        errors=errors,
    )
    for index, row in enumerate(validated_closure):
        dimension_id = row["dimension_id"]
        if dimension_id not in ALLOWED_CLOSURE_DIMENSION_IDS:
            errors.append(
                _cap_error(
                    path=f"closure_dimensions[{index}].dimension_id",
                    code="invalid",
                    message="dimension_id is not an allowed closure dimension",
                )
            )

    if errors:
        raise PublishPayloadValidationError(tuple(_bound_errors(errors)))

    return validated_scopes, validated_deps, validated_closure, validated_notes, validated_corrections


def validate_upstream_correction_rows_only(
    upstream_corrections: Any,
) -> list[dict[str, Any]]:
    """Validate only upstream_corrections rows (used before lineage checks)."""
    errors: list[dict[str, str]] = []
    correction_list, correction_type_errors = _require_row_list(
        upstream_corrections,
        field_name="upstream_corrections",
    )
    errors.extend(correction_type_errors)
    if len(correction_list) > MAX_UPSTREAM_CORRECTIONS:
        errors.append(
            _cap_error(
                path="upstream_corrections",
                code="cap_exceeded",
                message=f"upstream_corrections exceeds maximum of {MAX_UPSTREAM_CORRECTIONS} items",
            )
        )
    validated_corrections: list[dict[str, Any]] = []
    for index, row in enumerate(correction_list):
        validated, row_errors = _validate_row_at(
            UpstreamCorrectionRow,
            row,
            path_prefix=f"upstream_corrections[{index}]",
        )
        if validated is not None:
            validated_corrections.append(validated)
        errors.extend(row_errors)
    _collect_uniqueness_errors(
        [row["correction_id"] for row in validated_corrections],
        path="upstream_corrections",
        code="correction_id_not_unique",
        errors=errors,
    )
    if errors:
        raise PublishPayloadValidationError(tuple(_bound_errors(errors)))
    return validated_corrections


def _require_row_list(value: Any, *, field_name: str) -> tuple[list[Any], list[dict[str, str]]]:
    if value is None:
        return [], []
    if isinstance(value, list):
        return value, []
    return [], [
        _cap_error(
            path=field_name,
            code="invalid",
            message=f"{field_name} must be an array of row objects",
        )
    ]


def _validate_row_at(
    model_cls: type,
    row: Any,
    *,
    path_prefix: str,
) -> tuple[dict[str, Any] | None, list[dict[str, str]]]:
    if not isinstance(row, dict):
        return None, [
            _cap_error(
                path=path_prefix,
                code="invalid",
                message="Row must be an object",
            )
        ]
    try:
        return model_cls.model_validate(row).model_dump(mode="json"), []
    except ValidationError as exc:
        return None, _format_validation_errors(exc, path_prefix=path_prefix)


def _collect_uniqueness_errors(
    values: list[str],
    *,
    path: str,
    code: str,
    errors: list[dict[str, str]],
) -> None:
    if len(values) != len(set(values)):
        errors.append(
            _cap_error(
                path=path,
                code=code,
                message=f"{code.replace('_', ' ')}",
            )
        )


def _format_validation_errors(exc: ValidationError, *, path_prefix: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for err in exc.errors():
        loc = err.get("loc") or ()
        suffix = _format_loc(loc)
        path = f"{path_prefix}.{suffix}" if suffix else path_prefix
        rows.append(
            _cap_error(
                path=path,
                code=_error_code_from_pydantic(err),
                message=_error_message_from_pydantic(err),
            )
        )
    return rows


def _format_loc(loc: tuple[Any, ...]) -> str:
    parts: list[str] = []
    for part in loc:
        if isinstance(part, int):
            if parts:
                parts[-1] = f"{parts[-1]}[{part}]"
            else:
                parts.append(f"[{part}]")
        else:
            parts.append(str(part))
    return ".".join(parts).lstrip(".")


def _error_code_from_pydantic(err: dict[str, Any]) -> str:
    err_type = str(err.get("type") or "invalid")
    if err_type == "extra_forbidden":
        return "extra_forbidden"
    if err_type in {"missing"}:
        return "missing"
    if err_type in {"too_long", "string_too_long"}:
        return "too_long"
    if err_type in {"too_short", "string_too_short"}:
        return "too_short"
    if err_type == "list_type":
        return "invalid"
    if err_type == "model_type":
        return "invalid"
    return err_type.replace(".", "_")[:64] or "invalid"


def _error_message_from_pydantic(err: dict[str, Any]) -> str:
    msg = str(err.get("msg") or "invalid")
    if msg.startswith("Value error, "):
        msg = msg[len("Value error, ") :]
    if len(msg) > 240:
        msg = msg[:239].rstrip() + "…"
    return msg


def _cap_error(*, path: str, code: str, message: str) -> dict[str, str]:
    safe_path = _safe_validation_path(path)
    safe_message = message.strip() or code
    if len(safe_message) > 240:
        safe_message = safe_message[:239].rstrip() + "…"
    return {"path": safe_path, "code": code[:64], "message": safe_message}


def _safe_validation_path(path: str) -> str:
    cleaned = str(path or "").strip()
    if not cleaned:
        return "payload"
    if len(cleaned) > 256:
        return cleaned[:256]
    return cleaned


def _bound_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    if len(errors) <= MAX_PUBLISH_VALIDATION_ERRORS:
        return errors
    keep = MAX_PUBLISH_VALIDATION_ERRORS - 1
    bounded = errors[:keep]
    bounded.append(
        _cap_error(
            path="payload",
            code="validation_errors_truncated",
            message=f"{len(errors) - keep} additional validation errors omitted",
        )
    )
    return bounded


def list_valid_mapping_refs(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    limit: int = 8,
) -> list[str]:
    """List recent canonical mapping artifact refs for a dossier."""
    from feature_graph.artifact_refs import build_feature_graph_artifact_ref

    entries = persistence.list_artifacts(dossier_id=dossier_id, artifact_type="mapping")
    entries.sort(key=lambda item: str((item or {}).get("saved_at") or ""), reverse=True)
    refs: list[str] = []
    for entry in entries[: max(1, limit)]:
        artifact_id = str((entry or {}).get("artifact_id") or "").strip()
        if not artifact_id:
            continue
        refs.append(build_feature_graph_artifact_ref("mapping", artifact_id))
    return refs


def mapping_artifact_not_found_refusal(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    requested_ref: str | None = None,
) -> dict[str, Any]:
    code = "mapping_artifact_not_found"
    valid_mapping_refs = list_valid_mapping_refs(persistence=persistence, dossier_id=dossier_id)
    message = "Mapping artifact was not found in the current dossier."
    if requested_ref:
        message = f"Mapping artifact '{requested_ref}' was not found in the current dossier."
    return {
        "executed": False,
        "refusal": {
            "reason_code": code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {"code": code, "message": message},
            "valid_mapping_refs": valid_mapping_refs,
            "repair_hint": (
                "Use the full mapping_artifact_ref returned by submit_ir_for_mapping "
                "or mapping_review.recommended_publish_refs."
            ),
        },
    }
