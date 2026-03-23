"""Feature-graph terminal completion hooks.

Owned by the feature-graph domain/product layer, not ``agent_kernel.session``.
"""

from __future__ import annotations

from agent_kernel.run_artifact import RunArtifact
from services.feature_graph.feature_graph_persistence_service import FeatureGraphPersistenceService


def mark_final_feature_graph_pointers(run_artifact: RunArtifact) -> None:
    """Best-effort final pointer persistence for deed/feature-graph product wiring."""
    ir_path = run_artifact.ir_artifact_ref.artifact_path if run_artifact.ir_artifact_ref is not None else None
    bundle_path = (
        run_artifact.bundle_artifact_ref.artifact_path
        if run_artifact.bundle_artifact_ref is not None
        else None
    )
    if not ir_path:
        return
    FeatureGraphPersistenceService().mark_final_pointers_from_paths(
        ir_artifact_path=ir_path,
        bundle_artifact_path=bundle_path,
    )
