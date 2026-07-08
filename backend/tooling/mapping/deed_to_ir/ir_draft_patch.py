"""Surgical IR draft patching for deed-to-IR (mechanical merge, append-only save)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from services.feature_graph.feature_graph_evaluation_service import FeatureGraphEvaluationService
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

from .course_updates import apply_course_updates
from .draft_ir_lifecycle import load_base_draft_artifact, prior_graph_id_from_artifact
from .ir_persistence import _base_draft_refusal, _graph_id_mismatch_refusal, save_ir_artifact
from .patch_deep_merge import deep_merge_patch


def patch_ir_draft(
    *,
    dossier_id: str,
    base_draft_ref: str,
    node_upserts: Sequence[Mapping[str, Any]] | None = None,
    edge_upserts: Sequence[Mapping[str, Any]] | None = None,
    node_removals: Sequence[str] | None = None,
    edge_removals: Sequence[Mapping[str, Any]] | None = None,
    course_updates: Sequence[Mapping[str, Any]] | None = None,
    graph_id: str | None = None,
    draft_workspace_id: str | None = None,
    draft_run_id: str | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
    evaluation: FeatureGraphEvaluationService | None = None,
) -> dict[str, Any]:
    """Load a base draft, apply id-exact patches, validate, and save the next draft version."""
    if not dossier_id:
        raise ValueError("dossier_id_required")
    base_ref = str(base_draft_ref or "").strip()
    if not base_ref:
        raise ValueError("base_draft_ref_required")

    service = persistence or FeatureGraphPersistenceService()
    prior_artifact, base_error = load_base_draft_artifact(
        persistence=service,
        dossier_id=dossier_id,
        base_draft_ref=base_ref,
        draft_workspace_id=draft_workspace_id,
        draft_run_id=draft_run_id,
    )
    if base_error:
        return _base_draft_refusal(
            reason_code=base_error,
            message=f"Could not load base draft ref: {base_error}",
        )

    graph_raw = prior_artifact.get("graph") if isinstance(prior_artifact, Mapping) else None
    if not isinstance(graph_raw, Mapping):
        return _base_draft_refusal(
            reason_code="base_draft_graph_missing",
            message="Base draft artifact is missing a valid graph payload.",
        )

    expected_graph_id = prior_graph_id_from_artifact(prior_artifact)  # type: ignore[arg-type]
    if isinstance(graph_id, str) and graph_id.strip() and graph_id.strip() != expected_graph_id:
        return _graph_id_mismatch_refusal(
            expected_graph_id=expected_graph_id,
            actual_graph_id=graph_id.strip(),
        )

    working_graph = dict(graph_raw)
    if course_updates:
        course_patched, course_refusal = apply_course_updates(
            working_graph,
            course_updates=course_updates,
        )
        if course_refusal is not None:
            return course_refusal
        if course_patched is not None:
            working_graph = course_patched

    patched_graph, warnings = _apply_patch(
        working_graph,
        node_upserts=node_upserts or (),
        edge_upserts=edge_upserts or (),
        node_removals=node_removals or (),
        edge_removals=edge_removals or (),
    )
    if expected_graph_id:
        patched_graph["graph_id"] = expected_graph_id

    result = save_ir_artifact(
        dossier_id=dossier_id,
        feature_graph=patched_graph,
        base_draft_ref=base_ref,
        draft_workspace_id=draft_workspace_id,
        draft_run_id=draft_run_id,
        persistence=service,
        evaluation=evaluation,
    )
    if warnings and result.get("executed"):
        outputs = dict(result.get("outputs") or {})
        outputs["patch_warnings"] = warnings
        result = {**result, "outputs": outputs}
    return result


def _apply_patch(
    graph: dict[str, Any],
    *,
    node_upserts: Sequence[Mapping[str, Any]],
    edge_upserts: Sequence[Mapping[str, Any]],
    node_removals: Sequence[str],
    edge_removals: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, str]]]:
    warnings: list[dict[str, str]] = []
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    edges = graph.get("edges") if isinstance(graph.get("edges"), list) else []

    node_order = [str(node.get("id")) for node in nodes if isinstance(node, Mapping) and node.get("id")]
    nodes_by_id: dict[str, dict[str, Any]] = {
        str(node["id"]): dict(node)
        for node in nodes
        if isinstance(node, Mapping) and node.get("id")
    }

    for removal_id in node_removals:
        text = str(removal_id or "").strip()
        if not text:
            continue
        if text in nodes_by_id:
            del nodes_by_id[text]
            node_order = [node_id for node_id in node_order if node_id != text]
        else:
            warnings.append({"kind": "node_removal_noop", "node_id": text})

    for upsert in node_upserts:
        if not isinstance(upsert, Mapping):
            continue
        node_id = str(upsert.get("id") or "").strip()
        if not node_id:
            continue
        merged = deep_merge_patch(nodes_by_id.get(node_id, {}), dict(upsert))
        merged["id"] = node_id
        if node_id not in nodes_by_id and node_id not in node_order:
            node_order.append(node_id)
        nodes_by_id[node_id] = merged

    edges_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    edge_order: list[tuple[str, str, str]] = []
    for edge in edges:
        if not isinstance(edge, Mapping):
            continue
        key = _edge_key(edge)
        if key is None:
            continue
        if key not in edges_by_key:
            edge_order.append(key)
        edges_by_key[key] = dict(edge)

    for removal in edge_removals:
        if not isinstance(removal, Mapping):
            continue
        key = _edge_key(removal)
        if key is None:
            continue
        if key in edges_by_key:
            del edges_by_key[key]
            edge_order = [item for item in edge_order if item != key]
        else:
            warnings.append(
                {
                    "kind": "edge_removal_noop",
                    "source_id": key[0],
                    "target_id": key[1],
                    "edge_type": key[2],
                }
            )

    for upsert in edge_upserts:
        if not isinstance(upsert, Mapping):
            continue
        key = _edge_key(upsert)
        if key is None:
            continue
        merged = {**edges_by_key.get(key, {}), **dict(upsert)}
        merged["source_id"] = key[0]
        merged["target_id"] = key[1]
        merged["edge_type"] = key[2]
        if key not in edges_by_key and key not in edge_order:
            edge_order.append(key)
        edges_by_key[key] = merged

    patched = dict(graph)
    patched["nodes"] = [nodes_by_id[node_id] for node_id in node_order if node_id in nodes_by_id]
    patched["edges"] = [edges_by_key[key] for key in edge_order if key in edges_by_key]
    if "metadata" not in patched or not isinstance(patched.get("metadata"), dict):
        patched["metadata"] = graph.get("metadata") if isinstance(graph.get("metadata"), dict) else {}
    return patched, warnings


def _edge_key(edge: Mapping[str, Any]) -> tuple[str, str, str] | None:
    source_id = str(edge.get("source_id") or "").strip()
    target_id = str(edge.get("target_id") or "").strip()
    edge_type = str(edge.get("edge_type") or "depends_on").strip() or "depends_on"
    if not source_id or not target_id:
        return None
    return source_id, target_id, edge_type
