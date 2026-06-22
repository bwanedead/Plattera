"""Mapping artifact models for feature-graph render outputs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from .artifacts import ArtifactMetadata


class SkippedFeatureRecord(BaseModel):
    node_id: str = Field(..., description="Feature node ID that was skipped")
    graph_id: str = Field(..., description="Graph ID containing the node")
    kind: str = Field(..., description="Feature kind at skip time")
    reason: str = Field(..., description="Mechanical skip reason code")
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        frozen = False


class WorldBBox(BaseModel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    class Config:
        frozen = False


class GeometryArtifactDescriptor(BaseModel):
    ref: str = Field(..., description="Path-free sidecar ref")
    media_type: str = Field("application/geo+json")
    byte_count: int = Field(..., ge=0)
    sha256: str = Field(..., description="Hex digest of sidecar bytes")
    world_bbox: WorldBBox
    rendered_feature_count: int = Field(..., ge=0)
    skipped_feature_count: int = Field(..., ge=0)

    class Config:
        frozen = False


class RenderArtifactDescriptor(BaseModel):
    ref: str = Field(..., description="Path-free sidecar ref")
    media_type: str = Field("image/png")
    profile: Literal["clean", "control"]
    byte_count: int = Field(..., ge=0)
    sha256: str = Field(..., description="Hex digest of sidecar bytes")
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    world_bbox: WorldBBox

    class Config:
        frozen = False


class MappingArtifact(BaseModel):
    artifact_id: str
    artifact_type: Literal["mapping"] = "mapping"
    graph_id: str
    source_ir_artifact_id: str
    source_ir_artifact_ref: str
    compile_artifact_id: str
    compile_artifact_ref: str
    judge_artifact_id: str
    judge_artifact_ref: str
    geometry: GeometryArtifactDescriptor
    clean_render: RenderArtifactDescriptor
    control_render: RenderArtifactDescriptor
    coordinate_space: str
    world_bbox: WorldBBox
    rendered_feature_ids: list[str] = Field(default_factory=list)
    skipped_features: list[SkippedFeatureRecord] = Field(default_factory=list)
    gap_count: int = Field(0, ge=0)
    warning_count: int = Field(0, ge=0)
    metadata: ArtifactMetadata

    class Config:
        frozen = False


def create_mapping_artifact(
    *,
    artifact_id: str,
    graph_id: str,
    source_ir_artifact_id: str,
    source_ir_artifact_ref: str,
    compile_artifact_id: str,
    compile_artifact_ref: str,
    judge_artifact_id: str,
    judge_artifact_ref: str,
    geometry: GeometryArtifactDescriptor,
    clean_render: RenderArtifactDescriptor,
    control_render: RenderArtifactDescriptor,
    coordinate_space: str,
    world_bbox: WorldBBox,
    rendered_feature_ids: list[str] | None = None,
    skipped_features: list[SkippedFeatureRecord] | None = None,
    gap_count: int = 0,
    warning_count: int = 0,
    created_by: str | None = None,
    parent_artifact_ids: list[str] | None = None,
) -> MappingArtifact:
    metadata = ArtifactMetadata(
        created_at=datetime.utcnow().isoformat() + "Z",
        created_by=created_by,
        parent_artifact_ids=parent_artifact_ids or [],
        version="1.0",
    )
    return MappingArtifact(
        artifact_id=artifact_id,
        artifact_type="mapping",
        graph_id=graph_id,
        source_ir_artifact_id=source_ir_artifact_id,
        source_ir_artifact_ref=source_ir_artifact_ref,
        compile_artifact_id=compile_artifact_id,
        compile_artifact_ref=compile_artifact_ref,
        judge_artifact_id=judge_artifact_id,
        judge_artifact_ref=judge_artifact_ref,
        geometry=geometry,
        clean_render=clean_render,
        control_render=control_render,
        coordinate_space=coordinate_space,
        world_bbox=world_bbox,
        rendered_feature_ids=rendered_feature_ids or [],
        skipped_features=skipped_features or [],
        gap_count=gap_count,
        warning_count=warning_count,
        metadata=metadata,
    )
