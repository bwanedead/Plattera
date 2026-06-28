"""Feature-graph artifact listing and unified ref hydration for deed-to-IR tools."""

from __future__ import annotations

import base64
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from feature_graph.artifact_refs import (
    ARTIFACT_REF_PREFIXES,
    build_feature_graph_artifact_ref,
    parse_feature_graph_artifact_ref,
    validate_artifact_id,
)
from feature_graph.path_safety import require_safe_dossier_id
from services.feature_graph.feature_graph_mapping_sidecar_service import (
    FeatureGraphMappingSidecarService,
)
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

REF_PREFIXES = ARTIFACT_REF_PREFIXES
IR_REF_PREFIX = ARTIFACT_REF_PREFIXES["ir"]
DOSSIER_ARTIFACT_REF_PREFIX = "artifact://dossiers/"

DEFAULT_MAX_REFS = 8
MAX_REFS = 32
DEFAULT_LIST_LIMIT = 32
MAX_LIST_LIMIT = 64
MAX_HYDRATED_GRAPH_NODES = 128
MAX_HYDRATED_GRAPH_EDGES = 256
MAX_COMPILED_FEATURE_KEYS = 64
MAX_COMPILE_GAPS = 64
MAX_COMPILE_WARNINGS = 32
MAX_JUDGE_GAPS = 64
MAX_JUDGE_WARNINGS = 32
MAX_JUDGE_ARTIFACT_KEYS = 32
MAX_BUNDLE_DEPENDENCY_GRAPHS = 16
MAX_MAPPING_SKIPPED = 32
MAX_RENDERED_FEATURE_IDS = 64
MAX_GEOJSON_FEATURES = 64
ALLOWED_SIDECAR_NAMES = frozenset({"geometry.geojson", "clean.png", "control.png"})


def list_feature_graph_artifacts(
    *,
    dossier_id: str,
    artifact_type: str | None = None,
    limit: int = DEFAULT_LIST_LIMIT,
    persistence: FeatureGraphPersistenceService | None = None,
) -> dict[str, Any]:
    """List indexed feature-graph artifacts for a dossier (path-free)."""
    if not dossier_id:
        raise ValueError("dossier_id_required")
    cap = _clamp(limit, default=DEFAULT_LIST_LIMIT, maximum=MAX_LIST_LIMIT)
    service = persistence or FeatureGraphPersistenceService()
    entries = service.list_artifacts(dossier_id=dossier_id, artifact_type=artifact_type)  # type: ignore[arg-type]
    rows = [_index_entry_to_row(entry, persistence=service, dossier_id=dossier_id) for entry in entries[:cap]]
    return {
        "executed": True,
        "outputs": {
            "artifacts": rows,
            "count": len(rows),
            "total_indexed": len(entries),
            "truncated": len(entries) > cap,
        },
    }


def hydrate_artifact_refs(
    *,
    dossier_id: str,
    ref_ids: list[str],
    max_refs: int = DEFAULT_MAX_REFS,
    persistence: FeatureGraphPersistenceService | None = None,
    transcription_id: str | None = None,
    workspace_id: str | None = None,
    run_id: str | None = None,
    handoff_context: Mapping[str, Any] | None = None,
    working_draft_ref: str | None = None,
) -> dict[str, Any]:
    """Hydrate feature-graph, mapping sidecar, and deed-to-IR output refs without exposing paths."""
    return hydrate_feature_graph_artifact_refs(
        dossier_id=dossier_id,
        ref_ids=ref_ids,
        max_refs=max_refs,
        persistence=persistence,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        run_id=run_id,
        handoff_context=handoff_context,
        working_draft_ref=working_draft_ref,
    )


def make_hydrate_artifact_refs_handler(
    *,
    dossier_id: str,
    transcription_id: str | None = None,
    workspace_id: str | None = None,
    run_id: str | None = None,
    handoff_context: Mapping[str, Any] | None = None,
) -> Callable[[Any], Any]:
    """Return a handler for the canonical ``hydrate_artifact_refs`` tool ID."""

    def handler(request: Any) -> dict[str, Any]:
        inputs: dict[str, Any] = dict(request.inputs) if hasattr(request, "inputs") else dict(request) if isinstance(request, dict) else {}
        ref_ids = inputs.get("ref_ids")
        if not isinstance(ref_ids, list) or not ref_ids:
            return _refusal("ref_ids_required", "ref_ids must be a non-empty array.")
        try:
            return hydrate_artifact_refs(
                dossier_id=dossier_id,
                ref_ids=[str(item) for item in ref_ids if isinstance(item, str) and str(item).strip()],
                max_refs=inputs.get("max_refs"),
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                run_id=run_id,
                handoff_context=handoff_context,
                working_draft_ref=_optional_str(inputs.get("working_draft_ref")),
            )
        except Exception as exc:
            if isinstance(exc, ValueError) and str(exc).strip():
                return _refusal(str(exc).strip(), str(exc).strip())
            raise

    return handler


def hydrate_feature_graph_artifact_refs(
    *,
    dossier_id: str,
    ref_ids: list[str],
    max_refs: int = DEFAULT_MAX_REFS,
    persistence: FeatureGraphPersistenceService | None = None,
    transcription_id: str | None = None,
    workspace_id: str | None = None,
    run_id: str | None = None,
    handoff_context: Mapping[str, Any] | None = None,
    working_draft_ref: str | None = None,
) -> dict[str, Any]:
    """Hydrate feature-graph artifact refs without exposing filesystem paths."""
    if not dossier_id:
        raise ValueError("dossier_id_required")
    if not ref_ids:
        return _refusal("ref_ids_required", "ref_ids must be a non-empty array.")
    cap = _clamp(max_refs, default=DEFAULT_MAX_REFS, maximum=MAX_REFS)
    if len(ref_ids) > cap:
        return {
            "executed": True,
            "outputs": {
                "results": [],
                "errors": [{"reason": "cap_exceeded", "requested": len(ref_ids), "max_refs": cap}],
                "cap_exceeded": True,
                "hydrated_count": 0,
            },
        }
    service = persistence or FeatureGraphPersistenceService()
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=service.artifacts_root)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    image_evidence: list[dict[str, Any]] = []
    for ref_id in ref_ids:
        text = str(ref_id or "").strip()
        if text.startswith("deed_to_ir:operands"):
            row, error = _hydrate_operand_suite_ref(
                ref_id=text,
                handoff_context=handoff_context,
                run_id=run_id,
                workspace_id=workspace_id,
            )
            if row is not None:
                results.append(row)
            else:
                errors.append({"ref_id": text, "reason": error or "operand_suite_hydration_failed"})
            continue
        if text.startswith("deed_to_ir:output"):
            row, error = _hydrate_deed_to_ir_output_ref(
                dossier_id=dossier_id,
                ref_id=text,
                transcription_id=transcription_id,
                workspace_id=workspace_id,
                run_id=run_id,
            )
            if row is not None:
                results.append(row)
            else:
                errors.append({"ref_id": text, "reason": error or "output_hydration_failed"})
            continue
        if text.startswith(DOSSIER_ARTIFACT_REF_PREFIX):
            row, error, evidence = _hydrate_sidecar_ref(
                dossier_id=dossier_id,
                ref_id=text,
                sidecars=sidecars,
            )
            if row is not None:
                results.append(row)
                if evidence is not None:
                    image_evidence.append(evidence)
            else:
                errors.append({"ref_id": text, "reason": error or "sidecar_hydration_failed"})
            continue
        parsed = _parse_ref(text)
        if parsed is None:
            errors.append({"ref_id": text, "reason": "unsupported_ref_prefix"})
            continue
        artifact_type, artifact_id = parsed
        artifact = service.get_artifact(dossier_id, artifact_id)
        if not isinstance(artifact, dict):
            errors.append({"ref_id": text, "reason": "not_found"})
            continue
        if str(artifact.get("artifact_type") or "") != artifact_type:
            errors.append({"ref_id": text, "reason": "artifact_type_mismatch"})
            continue
        results.append(
            _hydrated_row(
                ref_id=text,
                artifact=artifact,
                dossier_id=dossier_id,
                persistence=service,
                working_draft_ref=working_draft_ref,
            )
        )
    payload: dict[str, Any] = {
        "executed": True,
        "outputs": {
            "results": results,
            "errors": errors,
            "cap_exceeded": False,
            "hydrated_count": len(results),
        },
    }
    if image_evidence:
        payload["image_evidence"] = image_evidence
    return payload


def _hydrated_row(
    *,
    ref_id: str,
    artifact: dict[str, Any],
    dossier_id: str | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
    working_draft_ref: str | None = None,
) -> dict[str, Any]:
    artifact_type = str(artifact.get("artifact_type") or "")
    row: dict[str, Any] = {
        "ref_id": ref_id,
        "artifact_type": artifact_type,
        "artifact_id": artifact.get("artifact_id"),
        "metadata": _strip_paths(artifact.get("metadata")),
    }
    if artifact_type == "ir":
        graph = artifact.get("graph") if isinstance(artifact.get("graph"), dict) else {}
        row["graph_id"] = graph.get("graph_id")
        bounded_graph, graph_meta = _bound_graph_dict(graph)
        row["graph"] = bounded_graph
        if graph_meta:
            row["graph"]["truncated"] = True
            row["truncated"] = graph_meta
        row["source_document_id"] = artifact.get("source_document_id")
        row["source_metadata"] = artifact.get("source_metadata")
    elif artifact_type == "compile":
        row["graph_id"] = artifact.get("graph_id")
        compiled = artifact.get("compiled_features")
        gaps = artifact.get("gaps")
        warnings = artifact.get("warnings")
        row["compiled_features"], cf_meta = _bound_mapping(compiled, MAX_COMPILED_FEATURE_KEYS)
        row["gaps"], gaps_meta = _bound_list(gaps, MAX_COMPILE_GAPS)
        row["warnings"], warnings_meta = _bound_list(warnings, MAX_COMPILE_WARNINGS)
        trunc = {k: v for k, v in (cf_meta | gaps_meta | warnings_meta).items() if v}
        if trunc:
            row["truncated"] = trunc
        row.update(
            _evaluation_artifact_labels(
                persistence=persistence,
                dossier_id=dossier_id,
                artifact=artifact,
                artifact_type=artifact_type,
                artifact_ref=ref_id,
                working_draft_ref=working_draft_ref,
            )
        )
    elif artifact_type == "judge":
        row["graph_id"] = artifact.get("graph_id")
        report = artifact.get("report") if isinstance(artifact.get("report"), dict) else {}
        bounded_report, report_meta = _bound_judge_report(report)
        row["report"] = bounded_report
        if report_meta:
            row["truncated"] = report_meta
        row.update(
            _evaluation_artifact_labels(
                persistence=persistence,
                dossier_id=dossier_id,
                artifact=artifact,
                artifact_type=artifact_type,
                artifact_ref=ref_id,
                working_draft_ref=working_draft_ref,
            )
        )
    elif artifact_type == "bundle":
        row["target_graph_id"] = artifact.get("target_graph_id")
        target = artifact.get("target_graph") if isinstance(artifact.get("target_graph"), dict) else {}
        row["target_graph"], tg_meta = _bound_graph_dict(target)
        deps = artifact.get("dependency_graphs")
        bounded_deps, deps_meta = _bound_dependency_graphs(deps)
        row["dependency_graphs"] = bounded_deps
        row["dependency_reasons"] = artifact.get("dependency_reasons")
        trunc = {k: v for k, v in (tg_meta | deps_meta).items() if v}
        if trunc:
            row["truncated"] = trunc
    elif artifact_type == "mapping":
        row["graph_id"] = artifact.get("graph_id")
        row["source_ir_artifact_ref"] = artifact.get("source_ir_artifact_ref")
        row["compile_artifact_ref"] = artifact.get("compile_artifact_ref")
        row["judge_artifact_ref"] = artifact.get("judge_artifact_ref")
        row["geometry"] = _strip_paths(artifact.get("geometry"))
        row["clean_render"] = _strip_paths(artifact.get("clean_render"))
        row["control_render"] = _strip_paths(artifact.get("control_render"))
        row["coordinate_space"] = artifact.get("coordinate_space")
        row["world_bbox"] = artifact.get("world_bbox")
        rendered_ids = artifact.get("rendered_feature_ids")
        skipped = artifact.get("skipped_features")
        row["rendered_feature_ids"], rendered_meta = _bound_list(rendered_ids, MAX_RENDERED_FEATURE_IDS)
        row["skipped_features"], skipped_meta = _bound_list(skipped, MAX_MAPPING_SKIPPED)
        row["gap_count"] = artifact.get("gap_count")
        row["warning_count"] = artifact.get("warning_count")
        trunc: dict[str, Any] = {}
        if rendered_meta:
            trunc["rendered_feature_ids"] = rendered_meta
        if skipped_meta:
            trunc["skipped_features"] = skipped_meta
        if trunc:
            row["truncated"] = trunc
        if persistence is not None and dossier_id:
            from .mapping_review import build_mapping_review_from_persisted_mapping

            review = build_mapping_review_from_persisted_mapping(
                mapping_raw=artifact,
                persistence=persistence,
                dossier_id=dossier_id,
            )
            if review is not None:
                row["mapping_review"] = review
    return _strip_paths(row)


def _hydrate_sidecar_ref(
    *,
    dossier_id: str,
    ref_id: str,
    sidecars: FeatureGraphMappingSidecarService,
) -> tuple[dict[str, Any] | None, str | None, dict[str, Any] | None]:
    try:
        parsed = _parse_sidecar_ref(dossier_id=dossier_id, ref_id=ref_id)
    except ValueError as exc:
        return None, str(exc), None
    if parsed is None:
        return None, "unsupported_sidecar_ref", None
    mapping_id, sidecar_name = parsed
    try:
        path = sidecars.resolve_existing_sidecar_path(dossier_id, mapping_id, sidecar_name)  # type: ignore[arg-type]
    except Exception:
        return None, "sidecar_not_found", None
    if sidecar_name == "geometry.geojson":
        try:
            return _hydrate_geojson_sidecar(ref_id=ref_id, path=path), None, None
        except ValueError:
            return None, "geojson_sidecar_invalid", None
    if sidecar_name in {"clean.png", "control.png"}:
        row = {
            "ref_id": ref_id,
            "artifact_type": "mapping_sidecar",
            "sidecar_name": sidecar_name,
            "media_type": "image/png",
        }
        evidence = _image_evidence_from_png(ref_id=ref_id, path=path)
        return row, None, evidence
    return None, "unsupported_sidecar_name", None


def resolve_sidecar_path_for_ref(
    *,
    dossier_id: str,
    ref_id: str,
    artifacts_root: Path | None = None,
) -> Path:
    parsed = _parse_sidecar_ref(dossier_id=dossier_id, ref_id=ref_id)
    if parsed is None:
        raise ValueError("unsupported_sidecar_ref")
    mapping_id, sidecar_name = parsed
    sidecars = FeatureGraphMappingSidecarService(artifacts_root=artifacts_root)
    return sidecars.resolve_existing_sidecar_path(dossier_id, mapping_id, sidecar_name)  # type: ignore[arg-type]


def _parse_sidecar_ref(*, dossier_id: str, ref_id: str) -> tuple[str, str] | None:
    text = str(ref_id or "").strip()
    if not text.startswith(DOSSIER_ARTIFACT_REF_PREFIX):
        return None
    relative = text[len(DOSSIER_ARTIFACT_REF_PREFIX) :]
    parts = [part for part in relative.replace("\\", "/").split("/") if part]
    if len(parts) != 5:
        return None
    root_segment, ref_dossier_id, mappings_segment, mapping_id, sidecar_name = parts
    if root_segment != "feature_graphs" or mappings_segment != "mappings":
        return None
    if sidecar_name not in ALLOWED_SIDECAR_NAMES:
        return None
    safe_dossier_id = require_safe_dossier_id(dossier_id)
    if require_safe_dossier_id(ref_dossier_id) != safe_dossier_id:
        raise ValueError("cross_dossier_ref")
    return validate_artifact_id(mapping_id), sidecar_name


def _hydrate_geojson_sidecar(*, ref_id: str, path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("geojson_sidecar_invalid") from exc
    if not isinstance(payload, dict):
        raise ValueError("geojson_sidecar_invalid")
    features = payload.get("features") if isinstance(payload.get("features"), list) else []
    bounded = features[:MAX_GEOJSON_FEATURES]
    return {
        "ref_id": ref_id,
        "artifact_type": "geometry_sidecar",
        "sidecar_name": "geometry.geojson",
        "media_type": "application/geo+json",
        "feature_collection": {
            "type": "FeatureCollection",
            "features": bounded,
        },
        "feature_count": len(features),
        "truncated": len(features) > MAX_GEOJSON_FEATURES,
    }


def image_evidence_from_png_path(*, ref_id: str, path: Path) -> dict[str, Any] | None:
    try:
        payload = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError:
        return None
    return {
        "ref_id": ref_id,
        "b64": payload,
        "media_type": "image/png",
    }


def _image_evidence_from_png(*, ref_id: str, path: Path) -> dict[str, Any] | None:
    return image_evidence_from_png_path(ref_id=ref_id, path=path)


def _bound_graph_dict(graph: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []
    meta: dict[str, Any] = {}
    bounded = {
        "graph_id": graph.get("graph_id"),
        "nodes": nodes[:MAX_HYDRATED_GRAPH_NODES],
        "edges": edges[:MAX_HYDRATED_GRAPH_EDGES],
        "metadata": graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {},
    }
    if len(nodes) > MAX_HYDRATED_GRAPH_NODES:
        meta["target_graph_nodes"] = True
        bounded["node_total"] = len(nodes)
    if len(edges) > MAX_HYDRATED_GRAPH_EDGES:
        meta["target_graph_edges"] = True
        bounded["edge_total"] = len(edges)
    return bounded, meta


def _bound_dependency_graphs(value: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(value, list):
        return [], {}
    meta: dict[str, Any] = {}
    graphs: list[dict[str, Any]] = []
    for entry in value[:MAX_BUNDLE_DEPENDENCY_GRAPHS]:
        if isinstance(entry, dict):
            bounded, _ = _bound_graph_dict(entry)
            graphs.append(bounded)
    if len(value) > MAX_BUNDLE_DEPENDENCY_GRAPHS:
        meta["dependency_graphs"] = True
        meta["dependency_graph_total"] = len(value)
    return graphs, meta


def _bound_judge_report(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    meta: dict[str, Any] = {}
    gaps, gaps_meta = _bound_list(report.get("gaps"), MAX_JUDGE_GAPS)
    warnings, warnings_meta = _bound_list(report.get("warnings"), MAX_JUDGE_WARNINGS)
    artifacts, artifacts_meta = _bound_mapping(report.get("artifacts"), MAX_JUDGE_ARTIFACT_KEYS)
    bounded = {
        "graph_id": report.get("graph_id"),
        "gaps": gaps,
        "warnings": warnings,
        "artifacts": artifacts,
        "metadata": report.get("metadata") if isinstance(report.get("metadata"), dict) else {},
    }
    combined = {**gaps_meta, **warnings_meta, **artifacts_meta}
    if combined:
        meta["report"] = combined
    return bounded, meta


def _bound_mapping(value: Any, cap: int) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(value, dict):
        return {}, {}
    keys = list(value.keys())
    if len(keys) <= cap:
        return dict(value), {}
    trimmed = {str(k): value[k] for k in keys[:cap]}
    return trimmed, {"truncated_keys": True, "total_keys": len(keys)}


def _bound_list(value: Any, cap: int) -> tuple[list[Any], dict[str, Any]]:
    if not isinstance(value, list):
        return [], {}
    if len(value) <= cap:
        return list(value), {}
    return list(value[:cap]), {"truncated": True, "total": len(value)}


def _index_entry_to_row(
    entry: dict[str, Any],
    *,
    persistence: FeatureGraphPersistenceService | None = None,
    dossier_id: str | None = None,
) -> dict[str, Any]:
    artifact_type = str(entry.get("artifact_type") or "")
    artifact_id = str(entry.get("artifact_id") or "")
    row: dict[str, Any] = {
        "artifact_ref": build_feature_graph_artifact_ref(artifact_type, artifact_id),
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "saved_at": entry.get("saved_at"),
    }
    if artifact_type == "ir" and persistence is not None and dossier_id:
        raw = persistence.get_artifact(dossier_id, artifact_id)
        if isinstance(raw, dict):
            meta = raw.get("source_metadata")
            if isinstance(meta, dict):
                if meta.get("draft_version"):
                    row["draft_version"] = meta.get("draft_version")
                if meta.get("draft_sequence_index") is not None:
                    row["draft_sequence_index"] = meta.get("draft_sequence_index")
                if meta.get("is_draft") is not None:
                    row["is_draft"] = meta.get("is_draft")
                if meta.get("draft_workspace_id"):
                    row["draft_workspace_id"] = meta.get("draft_workspace_id")
                if meta.get("draft_run_id"):
                    row["draft_run_id"] = meta.get("draft_run_id")
    return row


def _parse_ref(ref_id: str) -> tuple[str, str] | None:
    try:
        return parse_feature_graph_artifact_ref(ref_id)
    except ValueError:
        return None


def _strip_paths(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _strip_paths(v)
            for k, v in value.items()
            if str(k) not in {"artifact_path", "path"}
        }
    if isinstance(value, list):
        return [_strip_paths(item) for item in value]
    if isinstance(value, str) and _looks_like_path(value):
        return None
    return value


def _looks_like_path(value: str) -> bool:
    lowered = value.lower()
    return (
        lowered.startswith("c:\\")
        or lowered.startswith("/")
        or "\\" in value
        or (":/" in value and "feature_graph" not in lowered)
    )


def _clamp(value: Any, *, default: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 1:
        return default
    return min(parsed, maximum)


def _hydrate_operand_suite_ref(
    *,
    ref_id: str,
    handoff_context: Mapping[str, Any] | None,
    run_id: str | None,
    workspace_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    from .operand_suite import build_operand_suite_payload
    from .operand_suite_refs import (
        OPERAND_SUITE_REF,
        build_operand_suite_ref,
        parse_operand_suite_ref,
        validate_operand_suite_ref_access,
    )

    kind, _ = parse_operand_suite_ref(ref_id)
    if kind == "invalid":
        return None, "unsupported_operand_suite_ref"
    scope_error = validate_operand_suite_ref_access(
        ref_id,
        run_id=run_id,
        workspace_id=workspace_id,
    )
    if scope_error:
        return None, scope_error
    if handoff_context is None:
        return None, "operand_suite_context_unavailable"
    canonical_ref = build_operand_suite_ref(run_id=run_id, workspace_id=workspace_id)
    payload = build_operand_suite_payload(handoff_context, operand_suite_ref=canonical_ref)
    if payload is None:
        return None, "operand_suite_unavailable"
    if ref_id == OPERAND_SUITE_REF and payload.get("operand_suite_ref") != OPERAND_SUITE_REF:
        payload = {**payload, "operand_suite_ref": canonical_ref}
    return {
        "ref_id": ref_id,
        "artifact_type": "deed_to_ir_operand_suite",
        **payload,
    }, None


def _hydrate_deed_to_ir_output_ref(
    *,
    dossier_id: str,
    ref_id: str,
    transcription_id: str | None,
    workspace_id: str | None,
    run_id: str | None,
) -> tuple[dict[str, Any] | None, str | None]:
    from domains.mapping.deed_to_ir.payloads.published_output import (
        MAX_CLOSURE_DIMENSIONS,
        MAX_EXTERNAL_DEPENDENCIES,
        MAX_NOTES,
        MAX_SCOPE_RESULTS,
        DeedToIrPublishedOutput,
    )
    from .output_persistence import load_published_output, resolve_workspace_key
    from .output_refs import parse_output_ref

    if not str(transcription_id or "").strip():
        return None, "transcription_id_required"
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        return None, "workspace_identity_required"

    kind, revision_digits = parse_output_ref(ref_id)
    if kind == "invalid":
        return None, "unsupported_output_ref"
    if kind == "latest":
        revision_digits = None

    raw = load_published_output(
        dossier_id=dossier_id,
        transcription_id=str(transcription_id).strip(),
        workspace_id=workspace_key,
        revision_digits=revision_digits,
    )
    if raw is None:
        return None, "output_not_found"
    try:
        output = DeedToIrPublishedOutput.model_validate(raw)
    except Exception:
        return None, "output_invalid"

    scopes, scope_meta = _bound_list(
        [row.model_dump(mode="json") for row in output.scope_results],
        MAX_SCOPE_RESULTS,
    )
    deps, deps_meta = _bound_list(
        [row.model_dump(mode="json") for row in output.external_dependencies],
        MAX_EXTERNAL_DEPENDENCIES,
    )
    closure, closure_meta = _bound_list(
        [row.model_dump(mode="json") for row in output.closure_dimensions],
        MAX_CLOSURE_DIMENSIONS,
    )
    notes, notes_meta = _bound_list(
        [row.model_dump(mode="json") for row in output.notes],
        MAX_NOTES,
    )
    row: dict[str, Any] = {
        "ref_id": ref_id,
        "artifact_type": "deed_to_ir_output",
        "schema_version": output.schema_version,
        "source": output.source.model_dump(mode="json"),
        "selected_artifacts": output.selected_artifacts.model_dump(mode="json"),
        "scope_results": scopes,
        "external_dependencies": deps,
        "closure_dimensions": closure,
        "notes": notes,
    }
    trunc = {
        k: v
        for k, v in {
            "scope_results": scope_meta or None,
            "external_dependencies": deps_meta or None,
            "closure_dimensions": closure_meta or None,
            "notes": notes_meta or None,
        }.items()
        if v
    }
    if trunc:
        row["truncated"] = trunc
    return _strip_paths(row), None


def _evaluation_artifact_labels(
    *,
    persistence: FeatureGraphPersistenceService | None,
    dossier_id: str | None,
    artifact: dict[str, Any],
    artifact_type: str,
    artifact_ref: str,
    working_draft_ref: str | None,
) -> dict[str, Any]:
    if persistence is None or not dossier_id:
        return {"artifact_ref": artifact_ref}
    from .draft_artifact_lineage import build_evaluation_artifact_labels

    return build_evaluation_artifact_labels(
        persistence=persistence,
        dossier_id=dossier_id,
        artifact=artifact,
        artifact_type=artifact_type,
        artifact_ref=artifact_ref,
        working_draft_ref=working_draft_ref,
    )


def _optional_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


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
