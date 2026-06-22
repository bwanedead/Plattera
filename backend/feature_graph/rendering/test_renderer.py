"""Tests for clean/control rendering."""

from __future__ import annotations

import io
import tempfile
from pathlib import Path

from PIL import Image

from feature_graph.artifacts import create_compile_artifact, create_ir_artifact, create_judge_artifact
from feature_graph.gaps import JudgeReport
from feature_graph.models import FeatureGraph, FeatureKind, FeatureNode
from feature_graph.rendering.contracts import build_render_context
from feature_graph.rendering.geometry_projection import project_compiled_geometry
from feature_graph.rendering.renderer import (
    _control_label_position,
    render_clean_png,
    render_control_png,
)


def _sample_graph() -> FeatureGraph:
    return FeatureGraph(
        graph_id="render_sample",
        nodes=[
            FeatureNode(
                id="p1",
                kind=FeatureKind.POINT,
                label="POB",
                geometry={"type": "Point", "coordinates": [10.0, 10.0]},
            ),
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[10.0, 10.0], [110.0, 10.0]]},
            ),
            FeatureNode(
                id="region1",
                kind=FeatureKind.REGION,
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[10.0, 10.0], [110.0, 10.0], [110.0, 60.0], [10.0, 10.0]]],
                },
            ),
        ],
        edges=[],
    )


def _artifacts(graph: FeatureGraph):
    compiled = {}
    for node in graph.nodes:
        if node.geometry is not None:
            entry: dict = {"geometry": node.geometry, "source": "direct"}
            if node.id == "line1":
                entry["start_point"] = [10.0, 10.0]
                entry["end_point"] = [110.0, 10.0]
            compiled[node.id] = entry
    compile_artifact = create_compile_artifact(
        artifact_id="compile_render_sample",
        graph_id=graph.graph_id,
        compiled_features=compiled,
    )
    judge_artifact = create_judge_artifact(
        artifact_id="judge_render_sample",
        graph_id=graph.graph_id,
        report=JudgeReport(graph_id=graph.graph_id),
    )
    ir_artifact = create_ir_artifact(artifact_id="ir_render_sample", graph=graph)
    return ir_artifact, compile_artifact, judge_artifact


def test_clean_and_control_share_transform_and_geometry_pixels() -> None:
    graph = _sample_graph()
    ir_artifact, compile_artifact, judge_artifact = _artifacts(graph)
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    ctx = build_render_context(
        world_bounds=projection.world_bounds,
        coordinate_space=projection.coordinate_space,
    )
    clean = render_clean_png(
        projection=projection,
        graph=ir_artifact.graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    control = render_control_png(
        projection=projection,
        graph=ir_artifact.graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    clean_image = Image.open(io.BytesIO(clean)).convert("RGB")
    control_image = Image.open(io.BytesIO(control)).convert("RGB")
    assert clean_image.size == control_image.size == (ctx.canvas_width, ctx.canvas_height)

    sample_x, sample_y = ctx.world_to_canvas(60.0, 10.0)
    px = int(round(sample_x))
    py = int(round(sample_y))
    assert clean_image.getpixel((px, py)) == control_image.getpixel((px, py))
    assert clean != control


def test_images_are_nonblank_and_degenerate_point_only_renders() -> None:
    graph = FeatureGraph(
        graph_id="point_only",
        nodes=[
            FeatureNode(
                id="p1",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [5.0, 5.0]},
            )
        ],
        edges=[],
    )
    ir_artifact, compile_artifact, judge_artifact = _artifacts(graph)
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    clean = render_clean_png(
        projection=projection,
        graph=ir_artifact.graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    image = Image.open(io.BytesIO(clean)).convert("RGB")
    pixels = list(image.getdata())
    assert any(pixel != (255, 255, 255) for pixel in pixels)


def test_partial_compile_still_renders_available_geometry() -> None:
    graph = _sample_graph()
    compile_artifact = create_compile_artifact(
        artifact_id="compile_partial",
        graph_id=graph.graph_id,
        compiled_features={
            "p1": {"geometry": graph.nodes[0].geometry, "source": "direct"},
        },
        gaps=[{"kind": "unsupported_operation", "feature_id": "line1", "message": "missing"}],
    )
    judge_artifact = create_judge_artifact(
        artifact_id="judge_partial",
        graph_id=graph.graph_id,
        report=JudgeReport(graph_id=graph.graph_id),
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    clean = render_clean_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    assert len(projection.rendered_feature_ids) == 1
    assert len(clean) > 0


def test_degenerate_single_line_bounds_render_safely() -> None:
    graph = FeatureGraph(
        graph_id="single_line",
        nodes=[
            FeatureNode(
                id="line1",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0.0, 0.0], [0.0, 0.0]]},
            )
        ],
        edges=[],
    )
    compile_artifact = create_compile_artifact(
        artifact_id="compile_single_line",
        graph_id=graph.graph_id,
        compiled_features={"line1": {"geometry": graph.nodes[0].geometry, "source": "direct"}},
    )
    judge_artifact = create_judge_artifact(
        artifact_id="judge_single_line",
        graph_id=graph.graph_id,
        report=JudgeReport(graph_id=graph.graph_id),
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    ctx = build_render_context(
        world_bounds=projection.world_bounds,
        coordinate_space=projection.coordinate_space,
    )
    assert ctx.world_bounds.max_x - ctx.world_bounds.min_x > 0
    clean = render_clean_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    assert len(clean) > 0


def test_generate_representative_sample_pair_for_visual_inspection() -> None:
    graph = _sample_graph()
    ir_artifact, compile_artifact, judge_artifact = _artifacts(graph)
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    clean = render_clean_png(
        projection=projection,
        graph=ir_artifact.graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    control = render_control_png(
        projection=projection,
        graph=ir_artifact.graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        out = Path(tmpdir)
        (out / "clean.png").write_bytes(clean)
        (out / "control.png").write_bytes(control)
        assert (out / "clean.png").exists()
        assert (out / "control.png").exists()


def test_polygon_hole_renders_as_cutout_not_solid_fill() -> None:
    graph = FeatureGraph(
        graph_id="polygon_hole",
        nodes=[
            FeatureNode(
                id="donut",
                kind=FeatureKind.REGION,
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0], [0.0, 0.0]],
                        [[40.0, 40.0], [60.0, 40.0], [60.0, 60.0], [40.0, 60.0], [40.0, 40.0]],
                    ],
                },
            )
        ],
        edges=[],
    )
    compile_artifact = create_compile_artifact(
        artifact_id="compile_hole",
        graph_id=graph.graph_id,
        compiled_features={"donut": {"geometry": graph.nodes[0].geometry, "source": "direct"}},
    )
    judge_artifact = create_judge_artifact(
        artifact_id="judge_hole",
        graph_id=graph.graph_id,
        report=JudgeReport(graph_id=graph.graph_id),
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    ctx = build_render_context(
        world_bounds=projection.world_bounds,
        coordinate_space=projection.coordinate_space,
    )
    clean = render_clean_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    image = Image.open(io.BytesIO(clean)).convert("RGB")
    hole_x, hole_y = ctx.world_to_canvas(50.0, 50.0)
    fill_x, fill_y = ctx.world_to_canvas(10.0, 10.0)
    assert image.getpixel((int(round(hole_x)), int(round(hole_y)))) == (255, 255, 255)
    assert image.getpixel((int(round(fill_x)), int(round(fill_y)))) != (255, 255, 255)


def test_polygon_hole_preserves_underlying_line_geometry() -> None:
    graph = FeatureGraph(
        graph_id="polygon_hole_line",
        nodes=[
            FeatureNode(
                id="crossing_line",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[0.0, 50.0], [100.0, 50.0]]},
            ),
            FeatureNode(
                id="donut",
                kind=FeatureKind.REGION,
                geometry={
                    "type": "Polygon",
                    "coordinates": [
                        [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0], [0.0, 0.0]],
                        [[40.0, 40.0], [60.0, 40.0], [60.0, 60.0], [40.0, 60.0], [40.0, 40.0]],
                    ],
                },
            ),
        ],
        edges=[],
    )
    compile_artifact = create_compile_artifact(
        artifact_id="compile_hole_line",
        graph_id=graph.graph_id,
        compiled_features={
            "crossing_line": {"geometry": graph.nodes[0].geometry, "source": "direct"},
            "donut": {"geometry": graph.nodes[1].geometry, "source": "direct"},
        },
    )
    judge_artifact = create_judge_artifact(
        artifact_id="judge_hole_line",
        graph_id=graph.graph_id,
        report=JudgeReport(graph_id=graph.graph_id),
    )
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    ctx = build_render_context(
        world_bounds=projection.world_bounds,
        coordinate_space=projection.coordinate_space,
    )
    clean = render_clean_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    image = Image.open(io.BytesIO(clean)).convert("RGB")
    hole_x, hole_y = ctx.world_to_canvas(50.0, 50.0)
    hole_pixel = image.getpixel((int(round(hole_x)), int(round(hole_y))))
    assert hole_pixel != (255, 255, 255)
    assert hole_pixel[2] > hole_pixel[0]


def test_control_label_collision_uses_deterministic_offsets() -> None:
    anchor = (100.0, 100.0)
    occupied: dict[str, int] = {}
    first = _control_label_position(anchor, occupied=occupied)
    second = _control_label_position(anchor, occupied=occupied)
    third = _control_label_position(anchor, occupied=occupied)
    assert first != second != third
    assert first[1] + 14 == second[1]
    assert second[1] + 14 == third[1]


def test_control_labels_at_shared_anchor_render_without_error() -> None:
    graph = FeatureGraph(
        graph_id="shared_anchor",
        nodes=[
            FeatureNode(
                id="pob",
                kind=FeatureKind.POINT,
                geometry={"type": "Point", "coordinates": [10.0, 10.0]},
            ),
            FeatureNode(
                id="traverse",
                kind=FeatureKind.CURVE,
                geometry={"type": "LineString", "coordinates": [[10.0, 10.0], [110.0, 10.0]]},
            ),
            FeatureNode(
                id="parcel",
                kind=FeatureKind.REGION,
                geometry={
                    "type": "Polygon",
                    "coordinates": [[[10.0, 10.0], [110.0, 10.0], [110.0, 60.0], [10.0, 10.0]]],
                },
            ),
        ],
        edges=[],
    )
    ir_artifact, compile_artifact, judge_artifact = _artifacts(graph)
    projection = project_compiled_geometry(graph=graph, compile_artifact=compile_artifact)
    control = render_control_png(
        projection=projection,
        graph=ir_artifact.graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
    )
    assert len(projection.rendered_feature_ids) == 3
    assert len(control) > 0
