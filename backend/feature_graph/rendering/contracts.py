"""Shared contracts for geometry projection and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


DEFAULT_COORDINATE_SPACE = "unspecified_local"
CANVAS_WIDTH = 800
CANVAS_HEIGHT = 600
CANVAS_PADDING = 40
DEGENERATE_MIN_SPAN = 1.0

SUPPORTED_GEOMETRY_TYPES = frozenset({"Point", "LineString", "Polygon"})


@dataclass(frozen=True)
class WorldBounds:
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.min_x, self.min_y, self.max_x, self.max_y)

    def to_dict(self) -> dict[str, float]:
        return {
            "min_x": self.min_x,
            "min_y": self.min_y,
            "max_x": self.max_x,
            "max_y": self.max_y,
        }


@dataclass(frozen=True)
class SkippedFeature:
    node_id: str
    graph_id: str
    kind: str
    reason: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GeometryProjection:
    feature_collection: dict[str, Any]
    rendered_feature_ids: list[str]
    skipped_features: list[SkippedFeature]
    world_bounds: WorldBounds
    coordinate_space: str


@dataclass(frozen=True)
class RenderContext:
    world_bounds: WorldBounds
    canvas_width: int
    canvas_height: int
    padding: int
    scale: float
    offset_x: float
    offset_y: float
    coordinate_space: str

    def world_to_canvas(self, x: float, y: float) -> tuple[float, float]:
        bounds = self.world_bounds
        cx = self.offset_x + (x - bounds.min_x) * self.scale
        cy = self.offset_y + (bounds.max_y - y) * self.scale
        return (cx, cy)


def expand_degenerate_bounds(bounds: WorldBounds, *, min_span: float = DEGENERATE_MIN_SPAN) -> WorldBounds:
    min_x, min_y, max_x, max_y = bounds.as_tuple()
    if max_x - min_x < min_span:
        center_x = (min_x + max_x) / 2.0
        min_x = center_x - min_span / 2.0
        max_x = center_x + min_span / 2.0
    if max_y - min_y < min_span:
        center_y = (min_y + max_y) / 2.0
        min_y = center_y - min_span / 2.0
        max_y = center_y + min_span / 2.0
    return WorldBounds(min_x=min_x, min_y=min_y, max_x=max_x, max_y=max_y)


def bounds_from_coordinates(coords: list[tuple[float, float]]) -> WorldBounds | None:
    if not coords:
        return None
    xs = [point[0] for point in coords]
    ys = [point[1] for point in coords]
    return WorldBounds(min_x=min(xs), min_y=min(ys), max_x=max(xs), max_y=max(ys))


def merge_bounds(left: WorldBounds, right: WorldBounds) -> WorldBounds:
    return WorldBounds(
        min_x=min(left.min_x, right.min_x),
        min_y=min(left.min_y, right.min_y),
        max_x=max(left.max_x, right.max_x),
        max_y=max(left.max_y, right.max_y),
    )


def build_render_context(
    *,
    world_bounds: WorldBounds,
    coordinate_space: str,
    canvas_width: int = CANVAS_WIDTH,
    canvas_height: int = CANVAS_HEIGHT,
    padding: int = CANVAS_PADDING,
) -> RenderContext:
    expanded = expand_degenerate_bounds(world_bounds)
    inner_w = max(canvas_width - 2 * padding, 1)
    inner_h = max(canvas_height - 2 * padding, 1)
    world_w = max(expanded.max_x - expanded.min_x, 1e-9)
    world_h = max(expanded.max_y - expanded.min_y, 1e-9)
    scale = min(inner_w / world_w, inner_h / world_h)
    draw_w = world_w * scale
    draw_h = world_h * scale
    offset_x = padding + (inner_w - draw_w) / 2.0
    offset_y = padding + (inner_h - draw_h) / 2.0
    return RenderContext(
        world_bounds=expanded,
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        padding=padding,
        scale=scale,
        offset_x=offset_x,
        offset_y=offset_y,
        coordinate_space=coordinate_space,
    )


def resolve_coordinate_space(*sources: dict[str, Any] | None) -> str:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in ("coordinate_space", "frame_id", "crs"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return DEFAULT_COORDINATE_SPACE
