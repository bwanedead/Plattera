"""Mechanical parent-draft labels for compile/judge artifact hydration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from feature_graph.artifact_refs import build_feature_graph_artifact_ref

from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def build_evaluation_artifact_labels(
    *,
    persistence: FeatureGraphPersistenceService,
    dossier_id: str,
    artifact: Mapping[str, Any],
    artifact_type: str,
    artifact_ref: str,
    working_draft_ref: str | None = None,
) -> dict[str, Any]:
    """Label compile/judge hydration rows with parent IR draft generation context."""
    if artifact_type not in {"compile", "judge"}:
        return {}
    parent_ir_id = _resolve_parent_ir_artifact_id(artifact)
    if not parent_ir_id:
        return {"artifact_ref": artifact_ref}
    parent_raw = persistence.get_artifact(dossier_id, parent_ir_id)
    if not isinstance(parent_raw, Mapping):
        return {"artifact_ref": artifact_ref, "parent_ir_ref": build_feature_graph_artifact_ref("ir", parent_ir_id)}
    parent_ir_ref = build_feature_graph_artifact_ref("ir", parent_ir_id)
    source_meta = parent_raw.get("source_metadata") if isinstance(parent_raw.get("source_metadata"), Mapping) else {}
    graph = parent_raw.get("graph") if isinstance(parent_raw.get("graph"), Mapping) else {}
    parent_graph_id = graph.get("graph_id") or source_meta.get("graph_id")
    parent_draft_version = source_meta.get("draft_version")
    labels: dict[str, Any] = {
        "artifact_ref": artifact_ref,
        "parent_ir_ref": parent_ir_ref,
        "parent_graph_id": parent_graph_id,
        "parent_draft_version": parent_draft_version,
    }
    if isinstance(working_draft_ref, str) and working_draft_ref.strip():
        labels["is_current_for_working_draft"] = parent_ir_ref == working_draft_ref.strip()
    return labels


def _resolve_parent_ir_artifact_id(artifact: Mapping[str, Any]) -> str | None:
    metadata = artifact.get("metadata") if isinstance(artifact.get("metadata"), Mapping) else {}
    parents = metadata.get("parent_artifact_ids")
    if not isinstance(parents, list):
        return None
    for entry in parents:
        text = str(entry or "").strip()
        if text:
            return text
    return None
