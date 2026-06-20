"""IR artifact persistence for deed-to-IR (schema validation + save only)."""

from __future__ import annotations

import re
import uuid
from typing import Any

from feature_graph.artifact_refs import ARTIFACT_REF_PREFIXES, build_feature_graph_artifact_ref
from feature_graph.artifacts import create_ir_artifact
from feature_graph.models import FeatureGraph
from feature_graph.provenance import ProvenanceAttachment
from pydantic import ValidationError

from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService

IR_REF_PREFIX = ARTIFACT_REF_PREFIXES["ir"]


def save_ir_artifact(
    *,
    dossier_id: str,
    feature_graph: dict[str, Any],
    artifact_id: str | None = None,
    source_document_id: str | None = None,
    created_by: str | None = None,
    persistence: FeatureGraphPersistenceService | None = None,
) -> dict[str, Any]:
    """Validate and persist an agent-authored FeatureGraph; no compile/judge/render."""
    if not dossier_id:
        raise ValueError("dossier_id_required")
    if not isinstance(feature_graph, dict):
        return _validation_failure(["feature_graph must be an object"])
    try:
        graph = FeatureGraph.model_validate(feature_graph)
    except ValidationError as exc:
        return _validation_failure(_format_validation_errors(exc))

    resolved_artifact_id = _resolve_artifact_id(artifact_id=artifact_id, graph_id=graph.graph_id)
    link_count = _count_source_entity_links(graph)
    service = persistence or FeatureGraphPersistenceService()
    artifact = create_ir_artifact(
        artifact_id=resolved_artifact_id,
        graph=graph,
        created_by=created_by or "deed_to_ir_agent",
        source_document_id=source_document_id,
    )
    service.save_artifact(artifact, dossier_id=dossier_id)
    return {
        "executed": True,
        "artifact_refs": [build_feature_graph_artifact_ref("ir", resolved_artifact_id)],
        "outputs": {
            "ir_artifact_ref": build_feature_graph_artifact_ref("ir", resolved_artifact_id),
            "artifact_id": resolved_artifact_id,
            "graph_id": graph.graph_id,
            "node_count": len(graph.nodes),
            "edge_count": len(graph.edges),
            "source_entity_link_count": link_count,
            "validation_errors": [],
        },
    }


def _resolve_artifact_id(*, artifact_id: str | None, graph_id: str) -> str:
    if isinstance(artifact_id, str) and artifact_id.strip():
        return _sanitize_artifact_id(artifact_id.strip())
    suffix = uuid.uuid4().hex[:8]
    base = _sanitize_artifact_id(graph_id) or "graph"
    return f"ir_{base}_{suffix}"


def _sanitize_artifact_id(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("_")
    return cleaned[:128] or "ir_artifact"


def _count_source_entity_links(graph: FeatureGraph) -> int:
    total = 0
    for node in graph.nodes:
        total += _provenance_link_count(node.provenance)
    for edge in graph.edges:
        total += _provenance_link_count(edge.provenance)
    return total


def _provenance_link_count(provenance: Any) -> int:
    if provenance is None:
        return 0
    if isinstance(provenance, ProvenanceAttachment):
        return len(provenance.source_entity_links)
    if isinstance(provenance, dict):
        links = provenance.get("source_entity_links")
        return len(links) if isinstance(links, list) else 0
    return 0


def _validation_failure(errors: list[str]) -> dict[str, Any]:
    return {
        "executed": False,
        "outputs": {
            "validation_errors": errors,
            "ir_artifact_ref": None,
            "graph_id": None,
            "node_count": 0,
            "edge_count": 0,
            "source_entity_link_count": 0,
        },
    }


def _format_validation_errors(exc: ValidationError) -> list[str]:
    out: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        out.append(f"{loc}: {msg}" if loc else str(msg))
    return out
