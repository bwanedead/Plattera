"""Mechanical mapping creation from IR + compile + judge artifacts."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from feature_graph.artifact_refs import (
    build_feature_graph_artifact_ref,
    validate_artifact_id,
)
from feature_graph.artifacts import CompileArtifact, IRArtifact, JudgeArtifact
from feature_graph.mapping_artifacts import (
    MappingArtifact,
    SkippedFeatureRecord,
    WorldBBox,
    create_mapping_artifact,
)
from feature_graph.rendering.contracts import build_render_context
from feature_graph.rendering.geometry_projection import project_compiled_geometry
from feature_graph.rendering.renderer import render_clean_png, render_control_png

from .feature_graph_mapping_sidecar_service import FeatureGraphMappingSidecarService
from .feature_graph_persistence_service import FeatureGraphPersistenceService


@dataclass(frozen=True)
class MappingCreationOutcome:
    artifact_id: str
    artifact_ref: str
    graph_id: str
    artifact: MappingArtifact
    rendered_feature_count: int
    skipped_feature_count: int
    gap_count: int
    warning_count: int


def _require_exact_ir_parent(
    *,
    artifact: CompileArtifact | JudgeArtifact,
    ir_artifact_id: str,
    role: str,
) -> None:
    parents = [str(item) for item in (artifact.metadata.parent_artifact_ids or [])]
    if ir_artifact_id not in parents:
        raise ValueError(f"{role}_ir_parent_missing")


class FeatureGraphMappingService:
    """Build mapping artifacts and sidecars from existing compile/judge outputs."""

    def __init__(
        self,
        persistence: FeatureGraphPersistenceService,
        sidecars: FeatureGraphMappingSidecarService,
    ) -> None:
        self._persistence = persistence
        self._sidecars = sidecars

    def create_mapping_from_artifacts(
        self,
        *,
        ir_artifact: IRArtifact,
        compile_artifact: CompileArtifact,
        judge_artifact: JudgeArtifact,
        dossier_id: str,
        mapping_artifact_id: str | None = None,
        created_by: str | None = "feature_graph_mapping_service",
    ) -> MappingCreationOutcome:
        if compile_artifact.graph_id != ir_artifact.graph.graph_id:
            raise ValueError("compile_graph_id_mismatch")
        if judge_artifact.graph_id != ir_artifact.graph.graph_id:
            raise ValueError("judge_graph_id_mismatch")
        _require_exact_ir_parent(
            artifact=compile_artifact,
            ir_artifact_id=ir_artifact.artifact_id,
            role="compile",
        )
        _require_exact_ir_parent(
            artifact=judge_artifact,
            ir_artifact_id=ir_artifact.artifact_id,
            role="judge",
        )

        resolved_id = _resolve_mapping_artifact_id(
            graph_id=ir_artifact.graph.graph_id,
            explicit=mapping_artifact_id,
        )
        projection = project_compiled_geometry(
            graph=ir_artifact.graph,
            compile_artifact=compile_artifact,
        )
        render_context = build_render_context(
            world_bounds=projection.world_bounds,
            coordinate_space=projection.coordinate_space,
        )
        clean_png = render_clean_png(
            projection=projection,
            graph=ir_artifact.graph,
            compile_artifact=compile_artifact,
            judge_artifact=judge_artifact,
        )
        control_png = render_control_png(
            projection=projection,
            graph=ir_artifact.graph,
            compile_artifact=compile_artifact,
            judge_artifact=judge_artifact,
        )
        world_bbox = WorldBBox(**render_context.world_bounds.to_dict())
        sidecars = self._sidecars.persist_sidecars(
            dossier_id=dossier_id,
            mapping_id=resolved_id,
            geometry_geojson=projection.feature_collection,
            clean_png=clean_png,
            control_png=control_png,
            world_bbox=world_bbox,
            rendered_feature_count=len(projection.rendered_feature_ids),
            skipped_feature_count=len(projection.skipped_features),
            image_width=render_context.canvas_width,
            image_height=render_context.canvas_height,
        )
        parent_ids = [
            ir_artifact.artifact_id,
            compile_artifact.artifact_id,
            judge_artifact.artifact_id,
        ]
        mapping_artifact = create_mapping_artifact(
            artifact_id=resolved_id,
            graph_id=ir_artifact.graph.graph_id,
            source_ir_artifact_id=ir_artifact.artifact_id,
            source_ir_artifact_ref=build_feature_graph_artifact_ref("ir", ir_artifact.artifact_id),
            compile_artifact_id=compile_artifact.artifact_id,
            compile_artifact_ref=build_feature_graph_artifact_ref("compile", compile_artifact.artifact_id),
            judge_artifact_id=judge_artifact.artifact_id,
            judge_artifact_ref=build_feature_graph_artifact_ref("judge", judge_artifact.artifact_id),
            geometry=sidecars.geometry,
            clean_render=sidecars.clean_render,
            control_render=sidecars.control_render,
            coordinate_space=projection.coordinate_space,
            world_bbox=world_bbox,
            rendered_feature_ids=list(projection.rendered_feature_ids),
            skipped_features=[
                SkippedFeatureRecord(
                    node_id=item.node_id,
                    graph_id=item.graph_id,
                    kind=item.kind,
                    reason=item.reason,
                    metadata=dict(item.metadata),
                )
                for item in projection.skipped_features
            ],
            gap_count=len(compile_artifact.gaps) + len(judge_artifact.report.gaps),
            warning_count=len(compile_artifact.warnings) + len(judge_artifact.report.warnings),
            created_by=created_by,
            parent_artifact_ids=parent_ids,
        )
        self._persistence.save_artifact(artifact=mapping_artifact, dossier_id=dossier_id)
        return MappingCreationOutcome(
            artifact_id=resolved_id,
            artifact_ref=build_feature_graph_artifact_ref("mapping", resolved_id),
            graph_id=ir_artifact.graph.graph_id,
            artifact=mapping_artifact,
            rendered_feature_count=len(projection.rendered_feature_ids),
            skipped_feature_count=len(projection.skipped_features),
            gap_count=mapping_artifact.gap_count,
            warning_count=mapping_artifact.warning_count,
        )


def _resolve_mapping_artifact_id(*, graph_id: str, explicit: str | None) -> str:
    if isinstance(explicit, str) and explicit.strip():
        return validate_artifact_id(explicit.strip())
    suffix = uuid.uuid4().hex[:8]
    base = _sanitize_graph_id(graph_id)
    return validate_artifact_id(f"mapping_{base}_{suffix}")


def _sanitize_graph_id(graph_id: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(graph_id or "")).strip("_")
    return cleaned[:96] or "graph"
