"""Pillow-based clean and control map rendering."""

from __future__ import annotations

import io
import math
from typing import Any

from PIL import Image, ImageDraw

from feature_graph.artifacts import CompileArtifact, JudgeArtifact
from feature_graph.gaps import GapKind
from feature_graph.models import FeatureGraph, FeatureKind

from .contracts import GeometryProjection, RenderContext, build_render_context


_KIND_STYLES: dict[str, dict[str, Any]] = {
    FeatureKind.POINT.value: {"fill": (20, 20, 20), "radius": 4},
    FeatureKind.CURVE.value: {"stroke": (30, 64, 175), "width": 2},
    FeatureKind.REGION.value: {"stroke": (22, 101, 52), "fill": (220, 252, 231, 120), "width": 2},
    FeatureKind.FRAME.value: {"stroke": (120, 53, 15), "fill": (254, 243, 199, 100), "width": 2},
    FeatureKind.CONSTRAINT.value: {"stroke": (107, 114, 128), "width": 1},
    FeatureKind.ANNOTATION.value: {"stroke": (75, 85, 99), "width": 1},
    FeatureKind.UNKNOWN.value: {"stroke": (156, 163, 175), "width": 1},
}


def _style_for_kind(kind: str) -> dict[str, Any]:
    return _KIND_STYLES.get(kind, {"stroke": (55, 65, 81), "width": 2})


def _draw_point(draw: ImageDraw.ImageDraw, ctx: RenderContext, coords: list[float], style: dict[str, Any]) -> None:
    x, y = ctx.world_to_canvas(float(coords[0]), float(coords[1]))
    radius = int(style.get("radius", 4))
    bbox = [x - radius, y - radius, x + radius, y + radius]
    draw.ellipse(bbox, fill=style.get("fill", (20, 20, 20)))


def _draw_linestring(draw: ImageDraw.ImageDraw, ctx: RenderContext, coords: list[list[float]], style: dict[str, Any]) -> None:
    if len(coords) < 2:
        return
    points = [ctx.world_to_canvas(float(x), float(y)) for x, y in coords]
    draw.line(points, fill=style.get("stroke", (30, 64, 175)), width=int(style.get("width", 2)))


def _draw_polygon(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    rings: list[list[list[float]]],
    style: dict[str, Any],
) -> None:
    if not rings:
        return
    outer = rings[0]
    outer_points = [ctx.world_to_canvas(float(x), float(y)) for x, y in outer]
    fill = style.get("fill")
    stroke = style.get("stroke", (22, 101, 52))
    width = int(style.get("width", 2))
    if fill is not None and len(rings) > 1:
        mask = Image.new("L", image.size, 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.polygon(outer_points, fill=255)
        for hole in rings[1:]:
            hole_points = [ctx.world_to_canvas(float(x), float(y)) for x, y in hole]
            if len(hole_points) >= 3:
                mask_draw.polygon(hole_points, fill=0)

        fill_rgba = fill if isinstance(fill, tuple) and len(fill) == 4 else (*tuple(fill)[:3], 255)
        layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
        layer_draw = ImageDraw.Draw(layer)
        layer_draw.polygon(outer_points, fill=fill_rgba)
        red, green, blue, alpha = layer.split()
        masked_alpha = Image.composite(alpha, Image.new("L", image.size, 0), mask)
        layer = Image.merge("RGBA", (red, green, blue, masked_alpha))
        image.alpha_composite(layer)
        draw.polygon(outer_points, outline=stroke)
        return
    if fill is not None:
        draw.polygon(outer_points, fill=fill, outline=stroke)
    else:
        draw.line(outer_points + [outer_points[0]], fill=stroke, width=width)


def _draw_geometry(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    geometry: dict[str, Any],
    kind: str,
) -> None:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    style = _style_for_kind(kind)
    if geom_type == "Point" and isinstance(coords, list):
        _draw_point(draw, ctx, coords, style)
    elif geom_type == "LineString" and isinstance(coords, list):
        _draw_linestring(draw, ctx, coords, style)
    elif geom_type == "Polygon" and isinstance(coords, list):
        _draw_polygon(image, draw, ctx, coords, style)


def _draw_label(draw: ImageDraw.ImageDraw, ctx: RenderContext, text: str, anchor: tuple[float, float]) -> None:
    draw.text((anchor[0] + 4, anchor[1] - 12), text, fill=(31, 41, 55))


def _feature_anchor(ctx: RenderContext, geometry: dict[str, Any]) -> tuple[float, float] | None:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if geom_type == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return ctx.world_to_canvas(float(coords[0]), float(coords[1]))
    if geom_type == "LineString" and isinstance(coords, list) and coords:
        x, y = coords[0]
        return ctx.world_to_canvas(float(x), float(y))
    if geom_type == "Polygon" and isinstance(coords, list) and coords and coords[0]:
        x, y = coords[0][0]
        return ctx.world_to_canvas(float(x), float(y))
    return None


def _draw_clean_features(
    image: Image.Image,
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    projection: GeometryProjection,
) -> None:
    for feature in projection.feature_collection.get("features", []):
        if not isinstance(feature, dict):
            continue
        geometry = feature.get("geometry")
        properties = feature.get("properties") or {}
        if not isinstance(geometry, dict):
            continue
        kind = str(properties.get("kind") or FeatureKind.UNKNOWN.value)
        _draw_geometry(image, draw, ctx, geometry, kind)
        label = properties.get("label")
        if isinstance(label, str) and label.strip():
            anchor = _feature_anchor(ctx, geometry)
            if anchor is not None:
                _draw_label(draw, ctx, label.strip(), anchor)


def _control_label_position(
    anchor: tuple[float, float],
    *,
    occupied: dict[str, int],
    max_stack: int = 8,
) -> tuple[float, float]:
    bucket = f"{int(round(anchor[0]))}:{int(round(anchor[1]))}"
    slot = min(occupied.get(bucket, 0), max_stack - 1)
    occupied[bucket] = slot + 1
    return (anchor[0] + 6, anchor[1] + 6 + slot * 14)


def _draw_direction_markers(
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    start: list[float],
    end: list[float],
) -> None:
    sx, sy = ctx.world_to_canvas(float(start[0]), float(start[1]))
    ex, ey = ctx.world_to_canvas(float(end[0]), float(end[1]))
    draw.ellipse([sx - 3, sy - 3, sx + 3, sy + 3], fill=(16, 185, 129))
    draw.ellipse([ex - 3, ey - 3, ex + 3, ey + 3], fill=(239, 68, 68))
    angle = math.atan2(ey - sy, ex - sx)
    tip_x = ex + 8 * math.cos(angle)
    tip_y = ey + 8 * math.sin(angle)
    left_x = ex + 6 * math.cos(angle + 2.6)
    left_y = ey + 6 * math.sin(angle + 2.6)
    right_x = ex + 6 * math.cos(angle - 2.6)
    right_y = ey + 6 * math.sin(angle - 2.6)
    draw.polygon([(tip_x, tip_y), (left_x, left_y), (right_x, right_y)], fill=(239, 68, 68))


def _draw_course_arrows(draw: ImageDraw.ImageDraw, ctx: RenderContext, properties: dict[str, Any], geometry: dict[str, Any]) -> None:
    courses = properties.get("courses")
    coords = geometry.get("coordinates")
    if not isinstance(courses, list) or not isinstance(coords, list) or len(coords) < 2:
        return
    for idx, course in enumerate(courses):
        if idx + 1 >= len(coords):
            break
        start = coords[idx]
        end = coords[idx + 1]
        if isinstance(start, list) and isinstance(end, list) and len(start) >= 2 and len(end) >= 2:
            _draw_direction_markers(draw, ctx, start, end)


def _draw_vertex_markers(draw: ImageDraw.ImageDraw, ctx: RenderContext, geometry: dict[str, Any]) -> None:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if geom_type == "LineString" and isinstance(coords, list):
        for item in coords:
            if isinstance(item, list) and len(item) >= 2:
                x, y = ctx.world_to_canvas(float(item[0]), float(item[1]))
                draw.rectangle([x - 2, y - 2, x + 2, y + 2], outline=(99, 102, 241))
    elif geom_type == "Polygon" and isinstance(coords, list) and coords:
        ring = coords[0]
        if isinstance(ring, list):
            for item in ring:
                if isinstance(item, list) and len(item) >= 2:
                    x, y = ctx.world_to_canvas(float(item[0]), float(item[1]))
                    draw.rectangle([x - 2, y - 2, x + 2, y + 2], outline=(99, 102, 241))


def _draw_closure_residuals(
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    compile_artifact: CompileArtifact,
) -> None:
    for gap in compile_artifact.gaps or []:
        if not isinstance(gap, dict):
            continue
        if gap.get("kind") != GapKind.PRECONDITION_FAILED.value:
            continue
        metadata = gap.get("metadata") or {}
        start = metadata.get("start_point")
        end = metadata.get("end_point")
        if not (isinstance(start, list) and isinstance(end, list) and len(start) >= 2 and len(end) >= 2):
            continue
        sx, sy = ctx.world_to_canvas(float(start[0]), float(start[1]))
        ex, ey = ctx.world_to_canvas(float(end[0]), float(end[1]))
        draw.line([(sx, sy), (ex, ey)], fill=(220, 38, 38), width=2)
        draw.text((ex + 4, ey + 4), "closure", fill=(220, 38, 38))


def _draw_gap_markers(
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    projection: GeometryProjection,
    judge_artifact: JudgeArtifact,
) -> None:
    feature_by_id = {
        str((feature.get("properties") or {}).get("node_id")): feature
        for feature in projection.feature_collection.get("features", [])
        if isinstance(feature, dict)
    }
    for gap in judge_artifact.report.gaps:
        feature_id = gap.feature_id
        if not feature_id or feature_id not in feature_by_id:
            continue
        feature = feature_by_id[feature_id]
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        anchor = _feature_anchor(ctx, geometry)
        if anchor is None:
            continue
        draw.rectangle(
            [anchor[0] - 6, anchor[1] - 6, anchor[0] + 6, anchor[1] + 6],
            outline=(234, 88, 12),
            width=2,
        )
        draw.text((anchor[0] + 8, anchor[1] + 8), gap.kind.value, fill=(234, 88, 12))


def _draw_frame_and_tie_features(
    draw: ImageDraw.ImageDraw,
    ctx: RenderContext,
    graph: FeatureGraph,
    projection: GeometryProjection,
) -> None:
    rendered = {
        str((feature.get("properties") or {}).get("node_id"))
        for feature in projection.feature_collection.get("features", [])
        if isinstance(feature, dict)
    }
    for node in graph.nodes:
        if node.id not in rendered:
            continue
        is_frame = node.kind == FeatureKind.FRAME
        is_tie = bool(node.op_expr and node.op_expr.op_name == "TiedPoint")
        if not (is_frame or is_tie):
            continue
        for feature in projection.feature_collection.get("features", []):
            properties = (feature or {}).get("properties") or {}
            if properties.get("node_id") != node.id:
                continue
            geometry = feature.get("geometry")
            if not isinstance(geometry, dict):
                continue
            anchor = _feature_anchor(ctx, geometry)
            if anchor is None:
                continue
            tag = "frame" if is_frame else "tie"
            draw.text((anchor[0] + 8, anchor[1] - 16), tag, fill=(120, 53, 15))


def _draw_orientation_axes(draw: ImageDraw.ImageDraw, ctx: RenderContext) -> None:
    origin_x = ctx.padding
    origin_y = ctx.canvas_height - ctx.padding
    draw.line([(origin_x, origin_y), (origin_x + 40, origin_y)], fill=(55, 65, 81), width=2)
    draw.line([(origin_x, origin_y), (origin_x, origin_y - 40)], fill=(55, 65, 81), width=2)
    draw.text((origin_x + 44, origin_y - 8), "+X", fill=(55, 65, 81))
    draw.text((origin_x + 4, origin_y - 44), "+Y", fill=(55, 65, 81))
    if ctx.coordinate_space != "unspecified_local":
        draw.text((origin_x, origin_y + 6), ctx.coordinate_space, fill=(107, 114, 128))


def _draw_skipped_indicators(draw: ImageDraw.ImageDraw, ctx: RenderContext, projection: GeometryProjection) -> None:
    if not projection.skipped_features:
        return
    x = ctx.canvas_width - ctx.padding - 180
    y = ctx.padding
    draw.text((x, y), f"skipped: {len(projection.skipped_features)}", fill=(107, 114, 128))
    for idx, skipped in enumerate(projection.skipped_features[:5]):
        draw.text((x, y + 16 + idx * 14), f"{skipped.node_id}: {skipped.reason}", fill=(107, 114, 128))


def _render_png(
    *,
    projection: GeometryProjection,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact,
    judge_artifact: JudgeArtifact,
    profile: str,
) -> bytes:
    ctx = build_render_context(
        world_bounds=projection.world_bounds,
        coordinate_space=projection.coordinate_space,
    )
    image = Image.new("RGBA", (ctx.canvas_width, ctx.canvas_height), (255, 255, 255, 255))
    draw = ImageDraw.Draw(image)
    _draw_clean_features(image, draw, ctx, projection)
    if profile == "control":
        label_slots: dict[str, int] = {}
        control_features = [
            feature
            for feature in projection.feature_collection.get("features", [])
            if isinstance(feature, dict)
        ]
        control_features.sort(
            key=lambda feature: int((feature.get("properties") or {}).get("render_order", 0))
        )
        for feature in control_features:
            geometry = feature.get("geometry")
            properties = feature.get("properties") or {}
            if not isinstance(geometry, dict):
                continue
            node_id = str(properties.get("node_id") or "")
            anchor = _feature_anchor(ctx, geometry)
            if anchor is not None and node_id:
                label_x, label_y = _control_label_position(anchor, occupied=label_slots)
                draw.text((label_x, label_y), node_id, fill=(17, 24, 39))
            _draw_vertex_markers(draw, ctx, geometry)
            start = properties.get("start_point")
            end = properties.get("end_point")
            if isinstance(start, list) and isinstance(end, list):
                _draw_direction_markers(draw, ctx, start, end)
            _draw_course_arrows(draw, ctx, properties, geometry)
        _draw_closure_residuals(draw, ctx, compile_artifact)
        _draw_frame_and_tie_features(draw, ctx, graph, projection)
        _draw_gap_markers(draw, ctx, projection, judge_artifact)
        _draw_skipped_indicators(draw, ctx, projection)
        _draw_orientation_axes(draw, ctx)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def render_clean_png(
    *,
    projection: GeometryProjection,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact,
    judge_artifact: JudgeArtifact,
) -> bytes:
    return _render_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
        profile="clean",
    )


def render_control_png(
    *,
    projection: GeometryProjection,
    graph: FeatureGraph,
    compile_artifact: CompileArtifact,
    judge_artifact: JudgeArtifact,
) -> bytes:
    return _render_png(
        projection=projection,
        graph=graph,
        compile_artifact=compile_artifact,
        judge_artifact=judge_artifact,
        profile="control",
    )


def render_context_for_projection(projection: GeometryProjection) -> RenderContext:
    return build_render_context(
        world_bounds=projection.world_bounds,
        coordinate_space=projection.coordinate_space,
    )
