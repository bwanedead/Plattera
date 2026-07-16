"""Mechanical scope-candidate inventory for deed-to-IR finalization sessions.

Builds ``scope_ids`` as the sorted unique union of normalized identifier signals.
Never parses arbitrary summaries/rationale prose, never invents scope IDs, and
never infers scope status.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .finalization_session import SCOPE_INVENTORY_UNAVAILABLE
from .resolution_scope import normalize_scope_signal


def project_finalization_scope_inventory(
    *,
    ir_graph: Mapping[str, Any] | Any | None = None,
    mapping_artifact: Mapping[str, Any] | Any | None = None,
    correction_candidates: Sequence[Mapping[str, Any]] | None = None,
    dependency_candidates: Sequence[Mapping[str, Any]] | None = None,
    resolution_state_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Project mechanical ``scope_ids`` plus bounded diagnostics.

    Returns ``{"scope_ids": [...], "diagnostics": [...]}``.
    When no scope can be identified, ``scope_ids`` is empty and a
    ``scope_inventory_unavailable`` diagnostic is included so a future finalizer
    can refuse explicitly instead of asking the agent to invent IDs.

    Capacity capping and ``finalization_requirements_capacity_exceeded`` live in
    the session builder so oversize discovery is never silently truncated.
    """
    collected: set[str] = set()

    for raw in _ir_node_feature_identifiers(ir_graph):
        _add_normalized(collected, raw)

    for raw in _mapping_feature_identifiers(mapping_artifact):
        _add_normalized(collected, raw)

    for row in correction_candidates or ():
        if isinstance(row, Mapping):
            _add_normalized(collected, row.get("target_entity_id"))

    for row in dependency_candidates or ():
        if isinstance(row, Mapping):
            _add_normalized(collected, row.get("affected_scope"))

    for raw in _resolution_identifier_signals(resolution_state_snapshot):
        _add_normalized(collected, raw)

    scope_ids = sorted(collected)
    diagnostics: list[dict[str, Any]] = []
    if not scope_ids:
        diagnostics.append(
            {
                "code": SCOPE_INVENTORY_UNAVAILABLE,
                "message": (
                    "No mechanical scope identifiers could be normalized from IR nodes, "
                    "mapping feature ids, correction targets, dependency affected_scope, "
                    "or resolution item/scope fields. A future finalizer must refuse "
                    "explicitly; do not invent scope IDs."
                ),
            }
        )
    return {"scope_ids": scope_ids, "diagnostics": diagnostics}


def _add_normalized(collected: set[str], raw: Any) -> None:
    normalized = normalize_scope_signal(raw)
    if normalized:
        collected.add(normalized)


def _ir_node_feature_identifiers(ir_graph: Mapping[str, Any] | Any | None) -> list[str]:
    if ir_graph is None:
        return []
    nodes = getattr(ir_graph, "nodes", None)
    if nodes is None and isinstance(ir_graph, Mapping):
        nodes = ir_graph.get("nodes")
    if not isinstance(nodes, list):
        return []
    out: list[str] = []
    for node in nodes:
        node_id = _node_id(node)
        if node_id:
            out.append(node_id)
        feature_id = _feature_ref_id(node)
        if feature_id:
            out.append(feature_id)
        for entity_id in _source_entity_ids(node):
            out.append(entity_id)
    return out


def _node_id(node: Any) -> str | None:
    if isinstance(node, Mapping):
        text = str(node.get("id") or "").strip()
        return text or None
    text = str(getattr(node, "id", "") or "").strip()
    return text or None


def _feature_ref_id(node: Any) -> str | None:
    feature_ref = None
    if isinstance(node, Mapping):
        feature_ref = node.get("feature_ref")
    else:
        feature_ref = getattr(node, "feature_ref", None)
    if feature_ref is None:
        return None
    if isinstance(feature_ref, Mapping):
        text = str(feature_ref.get("feature_id") or "").strip()
        return text or None
    text = str(getattr(feature_ref, "feature_id", "") or "").strip()
    return text or None


def _source_entity_ids(node: Any) -> list[str]:
    provenance = None
    if isinstance(node, Mapping):
        provenance = node.get("provenance")
    else:
        provenance = getattr(node, "provenance", None)
    if provenance is None:
        return []
    links = None
    if isinstance(provenance, Mapping):
        links = provenance.get("source_entity_links")
    else:
        links = getattr(provenance, "source_entity_links", None)
    if not isinstance(links, list):
        return []
    out: list[str] = []
    for link in links:
        if isinstance(link, Mapping):
            text = str(link.get("entity_id") or "").strip()
        else:
            text = str(getattr(link, "entity_id", "") or "").strip()
        if text:
            out.append(text)
    return out


def _mapping_feature_identifiers(mapping_artifact: Mapping[str, Any] | Any | None) -> list[str]:
    artifact = _unwrap_mapping_artifact(mapping_artifact)
    if artifact is None:
        return []
    rendered = getattr(artifact, "rendered_feature_ids", None)
    if rendered is None and isinstance(artifact, Mapping):
        rendered = artifact.get("rendered_feature_ids")
    skipped = getattr(artifact, "skipped_features", None)
    if skipped is None and isinstance(artifact, Mapping):
        skipped = artifact.get("skipped_features")

    out: list[str] = []
    if isinstance(rendered, list):
        for item in rendered:
            text = str(item or "").strip()
            if text:
                out.append(text)
    if isinstance(skipped, list):
        for row in skipped:
            if isinstance(row, Mapping):
                text = str(row.get("node_id") or "").strip()
            else:
                text = str(getattr(row, "node_id", "") or "").strip()
            if text:
                out.append(text)
    return out


def _unwrap_mapping_artifact(mapping_artifact: Mapping[str, Any] | Any | None) -> Any | None:
    """Prefer the underlying MappingArtifact when a submission wrapper is passed."""
    if mapping_artifact is None:
        return None
    if _has_mapping_feature_ids(mapping_artifact):
        return mapping_artifact
    nested = getattr(mapping_artifact, "artifact", None)
    if nested is not None and _has_mapping_feature_ids(nested):
        return nested
    if isinstance(mapping_artifact, Mapping):
        nested_map = mapping_artifact.get("artifact")
        if nested_map is not None and _has_mapping_feature_ids(nested_map):
            return nested_map
    return mapping_artifact


def _has_mapping_feature_ids(value: Any) -> bool:
    rendered = getattr(value, "rendered_feature_ids", None)
    if rendered is None and isinstance(value, Mapping):
        rendered = value.get("rendered_feature_ids")
    skipped = getattr(value, "skipped_features", None)
    if skipped is None and isinstance(value, Mapping):
        skipped = value.get("skipped_features")
    return isinstance(rendered, list) or isinstance(skipped, list)


def _resolution_identifier_signals(
    snapshot: Mapping[str, Any] | None,
) -> list[str]:
    """Collect identifier-like signals only — never summary/rationale prose."""
    if not isinstance(snapshot, Mapping):
        return []
    out: list[str] = []
    items = snapshot.get("items")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, Mapping):
                continue
            item_id = str(item.get("item_id") or "").strip()
            if item_id:
                out.append(item_id)
            for key in ("scope_id", "affected_scope", "parcel_id"):
                raw = item.get(key)
                if raw is not None and not isinstance(raw, (dict, list)):
                    text = str(raw).strip()
                    if text:
                        out.append(text)
    return out
