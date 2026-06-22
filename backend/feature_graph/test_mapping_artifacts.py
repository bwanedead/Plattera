"""Tests for mapping artifact models."""

from __future__ import annotations

import json

from feature_graph.artifact_refs import build_feature_graph_artifact_ref, parse_feature_graph_artifact_ref
from feature_graph.mapping_artifacts import (
    GeometryArtifactDescriptor,
    MappingArtifact,
    RenderArtifactDescriptor,
    SkippedFeatureRecord,
    WorldBBox,
    create_mapping_artifact,
)


def _world_bbox() -> WorldBBox:
    return WorldBBox(min_x=0.0, min_y=0.0, max_x=100.0, max_y=100.0)


def _geometry_descriptor() -> GeometryArtifactDescriptor:
    return GeometryArtifactDescriptor(
        ref="artifact://dossiers/feature_graphs/D1/mappings/m1/geometry.geojson",
        media_type="application/geo+json",
        byte_count=128,
        sha256="abc123",
        world_bbox=_world_bbox(),
        rendered_feature_count=2,
        skipped_feature_count=1,
    )


def _render_descriptor(profile: str) -> RenderArtifactDescriptor:
    return RenderArtifactDescriptor(
        ref=f"artifact://dossiers/feature_graphs/D1/mappings/m1/{profile}.png",
        media_type="image/png",
        profile=profile,  # type: ignore[arg-type]
        byte_count=2048,
        sha256=f"{profile}_hash",
        width=800,
        height=600,
        world_bbox=_world_bbox(),
    )


def test_mapping_artifact_json_round_trip() -> None:
    artifact = create_mapping_artifact(
        artifact_id="mapping_parcel_001",
        graph_id="parcel_a",
        source_ir_artifact_id="ir_parcel_a",
        source_ir_artifact_ref=build_feature_graph_artifact_ref("ir", "ir_parcel_a"),
        compile_artifact_id="compile_parcel_a",
        compile_artifact_ref=build_feature_graph_artifact_ref("compile", "compile_parcel_a"),
        judge_artifact_id="judge_parcel_a",
        judge_artifact_ref=build_feature_graph_artifact_ref("judge", "judge_parcel_a"),
        geometry=_geometry_descriptor(),
        clean_render=_render_descriptor("clean"),
        control_render=_render_descriptor("control"),
        coordinate_space="unspecified_local",
        world_bbox=_world_bbox(),
        rendered_feature_ids=["p1", "line1"],
        skipped_features=[
            SkippedFeatureRecord(
                node_id="group1",
                graph_id="parcel_a",
                kind="annotation",
                reason="semantic_group",
            )
        ],
        gap_count=1,
        warning_count=2,
        parent_artifact_ids=["ir_parcel_a", "compile_parcel_a", "judge_parcel_a"],
    )
    payload = json.loads(artifact.model_dump_json())
    rehydrated = MappingArtifact.model_validate(payload)
    assert rehydrated.artifact_type == "mapping"
    assert rehydrated.rendered_feature_ids == ["p1", "line1"]
    assert rehydrated.skipped_features[0].reason == "semantic_group"
    assert "correct" not in payload
    assert "map_ready" not in payload


def test_mapping_ref_build_and_parse() -> None:
    ref = build_feature_graph_artifact_ref("mapping", "mapping_parcel_001")
    artifact_type, artifact_id = parse_feature_graph_artifact_ref(ref)
    assert artifact_type == "mapping"
    assert artifact_id == "mapping_parcel_001"
