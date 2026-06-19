"""Feature-graph artifact listing and ref hydration for deed-to-IR tools."""

from __future__ import annotations

import re
from typing import Any

from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .ir_persistence import IR_REF_PREFIX

REF_PREFIXES = {
    "ir": IR_REF_PREFIX,
    "compile": "feature_graph:compile:",
    "judge": "feature_graph:judge:",
    "bundle": "feature_graph:bundle:",
}

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
    rows = [_index_entry_to_row(entry) for entry in entries[:cap]]
    return {
        "executed": True,
        "outputs": {
            "artifacts": rows,
            "count": len(rows),
            "total_indexed": len(entries),
            "truncated": len(entries) > cap,
        },
    }


def hydrate_feature_graph_artifact_refs(
    *,
    dossier_id: str,
    ref_ids: list[str],
    max_refs: int = DEFAULT_MAX_REFS,
    persistence: FeatureGraphPersistenceService | None = None,
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
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for ref_id in ref_ids:
        parsed = _parse_ref(ref_id)
        if parsed is None:
            errors.append({"ref_id": ref_id, "reason": "unsupported_ref_prefix"})
            continue
        artifact_type, artifact_id = parsed
        artifact = service.get_artifact(dossier_id, artifact_id)
        if not isinstance(artifact, dict):
            errors.append({"ref_id": ref_id, "reason": "not_found"})
            continue
        if str(artifact.get("artifact_type") or "") != artifact_type:
            errors.append({"ref_id": ref_id, "reason": "artifact_type_mismatch"})
            continue
        results.append(_hydrated_row(ref_id=ref_id, artifact=artifact))
    return {
        "executed": True,
        "outputs": {
            "results": results,
            "errors": errors,
            "cap_exceeded": False,
            "hydrated_count": len(results),
        },
    }


def _hydrated_row(*, ref_id: str, artifact: dict[str, Any]) -> dict[str, Any]:
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
    elif artifact_type == "judge":
        row["graph_id"] = artifact.get("graph_id")
        report = artifact.get("report") if isinstance(artifact.get("report"), dict) else {}
        bounded_report, report_meta = _bound_judge_report(report)
        row["report"] = bounded_report
        if report_meta:
            row["truncated"] = report_meta
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
    return _strip_paths(row)


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


def _index_entry_to_row(entry: dict[str, Any]) -> dict[str, Any]:
    artifact_type = str(entry.get("artifact_type") or "")
    artifact_id = str(entry.get("artifact_id") or "")
    prefix = REF_PREFIXES.get(artifact_type, f"feature_graph:{artifact_type}:")
    return {
        "artifact_ref": f"{prefix}{artifact_id}",
        "artifact_id": artifact_id,
        "artifact_type": artifact_type,
        "saved_at": entry.get("saved_at"),
    }


def _parse_ref(ref_id: str) -> tuple[str, str] | None:
    text = str(ref_id or "").strip()
    for artifact_type, prefix in REF_PREFIXES.items():
        if text.startswith(prefix):
            artifact_id = text[len(prefix) :].strip()
            if artifact_id and re.fullmatch(r"[A-Za-z0-9._-]+", artifact_id):
                return artifact_type, artifact_id
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
