"""Deterministic feature-graph geometry projection and dual-profile rendering."""

from .contracts import (
    GeometryProjection,
    RenderContext,
    SkippedFeature,
    WorldBounds,
)
from .geometry_projection import project_compiled_geometry
from .renderer import render_clean_png, render_control_png

__all__ = [
    "GeometryProjection",
    "RenderContext",
    "SkippedFeature",
    "WorldBounds",
    "project_compiled_geometry",
    "render_clean_png",
    "render_control_png",
]
