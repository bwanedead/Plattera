"""Mechanical root-source projection for nested point-crop geometry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .artifact_hydration import _load_derived_image_descriptor
from .image_loading import hydrate_source_image_context

_IMAGE_ASSOC_PREFIX = "image:assoc:"
_IMAGE_DERIVED_PREFIX = "image:derived:"
_MAX_CHAIN_DEPTH = 16
_ROUND = 6

_UNSUPPORTED_PROJECTION_SUB_ACTIONS = frozenset({
    "annotate",
    "reference_overlay",
    "render_evidence_locators",
    "point_crops",
    "point_crops_adjust",
    "point_crops_view",
    "expand",
})


@dataclass(frozen=True)
class ProjectionContext:
    local_source_ref: str
    root_source_ref: str | None
    local_width_height: list[int] | None
    root_width_height: list[int] | None
    projection_available: bool
    projection_unavailable_reason: str | None
    projection_chain: list[dict[str, Any]] = field(default_factory=list)


def _round_norm(values: list[float]) -> list[float]:
    return [round(float(v), _ROUND) for v in values]


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _compose_norm_through_link(x: float, y: float, link: dict[str, Any]) -> tuple[float, float] | None:
    sub_action = str(link.get("sub_action") or "").strip()
    meta = link.get("transform_metadata")
    if not isinstance(meta, dict):
        meta = {}

    if sub_action == "crop":
        box_norm = _link_box_norm(link)
        if box_norm is None:
            return None
        x1, y1, x2, y2 = box_norm
        return (
            x1 + x * (x2 - x1),
            y1 + y * (y2 - y1),
        )

    if sub_action == "zoom":
        box_norm = _link_box_norm(link)
        if box_norm is not None:
            x1, y1, x2, y2 = box_norm
            return (
                x1 + x * (x2 - x1),
                y1 + y * (y2 - y1),
            )
        if meta.get("factor_applied") is not None and _link_box_norm(link) is None:
            return x, y
        return None

    if sub_action == "point_crops_crop":
        box_norm = meta.get("box_norm")
        if not isinstance(box_norm, (list, tuple)) or len(box_norm) != 4:
            return None
        x1, y1, x2, y2 = (float(v) for v in box_norm)
        return (
            x1 + x * (x2 - x1),
            y1 + y * (y2 - y1),
        )

    return None


def _link_box_norm(link: dict[str, Any]) -> list[float] | None:
    meta = link.get("transform_metadata")
    if not isinstance(meta, dict):
        return None
    resolved = meta.get("resolved_geometry")
    if isinstance(resolved, dict) and isinstance(resolved.get("box_norm"), (list, tuple)):
        vals = resolved.get("box_norm")
        if vals and len(vals) == 4:
            return [float(v) for v in vals]
    if isinstance(meta.get("box_norm"), (list, tuple)) and len(meta["box_norm"]) == 4:
        return [float(v) for v in meta["box_norm"]]
    return None


def compose_point_norm_to_root(
    local_point_norm: list[float],
    projection_chain: list[dict[str, Any]],
) -> list[float] | None:
    if len(local_point_norm) != 2:
        return None
    x, y = float(local_point_norm[0]), float(local_point_norm[1])
    for link in projection_chain:
        mapped = _compose_norm_through_link(x, y, link)
        if mapped is None:
            return None
        x, y = mapped
    return _round_norm([_clamp01(x), _clamp01(y)])


def compose_box_norm_to_root(
    local_box_norm: list[float],
    projection_chain: list[dict[str, Any]],
) -> list[float] | None:
    if len(local_box_norm) != 4:
        return None
    corners = [
        (float(local_box_norm[0]), float(local_box_norm[1])),
        (float(local_box_norm[2]), float(local_box_norm[3])),
    ]
    mapped_corners: list[tuple[float, float]] = []
    for x, y in corners:
        px, py = x, y
        for link in projection_chain:
            step = _compose_norm_through_link(px, py, link)
            if step is None:
                return None
            px, py = step
        mapped_corners.append((_clamp01(px), _clamp01(py)))
    xs = [c[0] for c in mapped_corners]
    ys = [c[1] for c in mapped_corners]
    return _round_norm([min(xs), min(ys), max(xs), max(ys)])


def _root_dimensions(
    *,
    dossier_id: str,
    transcription_id: str,
    root_source_ref: str,
) -> list[int] | None:
    raw = hydrate_source_image_context(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        ref_id=root_source_ref,
    )
    if raw.get("status") != "ok" or not raw.get("exists"):
        return None
    wh = raw.get("width_height")
    if isinstance(wh, (list, tuple)) and len(wh) == 2:
        try:
            return [int(wh[0]), int(wh[1])]
        except (TypeError, ValueError):
            pass
    path = raw.get("absolute_path")
    if path:
        try:
            from PIL import Image

            with Image.open(Path(str(path))) as im:
                return [int(im.width), int(im.height)]
        except Exception:
            return None
    return None


def resolve_root_projection_context(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_key: str,
    source_ref: str,
    local_width_height: list[int] | None = None,
) -> ProjectionContext:
    """Inspect descriptor chain for local -> root coordinate projection."""
    local_ref = str(source_ref or "").strip()
    if not local_ref:
        return ProjectionContext(
            local_source_ref=local_ref,
            root_source_ref=None,
            local_width_height=local_width_height,
            root_width_height=None,
            projection_available=False,
            projection_unavailable_reason="source_ref is missing",
        )

    if local_ref.startswith(_IMAGE_ASSOC_PREFIX):
        root_wh = local_width_height or _root_dimensions(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            root_source_ref=local_ref,
        )
        return ProjectionContext(
            local_source_ref=local_ref,
            root_source_ref=local_ref,
            local_width_height=local_width_height or root_wh,
            root_width_height=root_wh,
            projection_available=True,
            projection_unavailable_reason=None,
            projection_chain=[],
        )

    if not local_ref.startswith(_IMAGE_DERIVED_PREFIX):
        return ProjectionContext(
            local_source_ref=local_ref,
            root_source_ref=None,
            local_width_height=local_width_height,
            root_width_height=None,
            projection_available=False,
            projection_unavailable_reason="unsupported source ref kind for projection",
        )

    chain: list[dict[str, Any]] = []
    current_ref = local_ref
    seen: set[str] = set()

    while current_ref.startswith(_IMAGE_DERIVED_PREFIX):
        if current_ref in seen or len(chain) >= _MAX_CHAIN_DEPTH:
            return ProjectionContext(
                local_source_ref=local_ref,
                root_source_ref=None,
                local_width_height=local_width_height,
                root_width_height=None,
                projection_available=False,
                projection_unavailable_reason="projection chain depth exceeded or cyclic parent_ref_id",
                projection_chain=chain,
            )
        seen.add(current_ref)

        desc = _load_derived_image_descriptor(dossier_id, transcription_id, workspace_key, current_ref)
        if desc is None:
            return ProjectionContext(
                local_source_ref=local_ref,
                root_source_ref=None,
                local_width_height=local_width_height,
                root_width_height=None,
                projection_available=False,
                projection_unavailable_reason=f"derived descriptor not found for {current_ref}",
                projection_chain=chain,
            )

        sub_action = str(desc.get("sub_action") or "").strip()
        parent_ref = str(desc.get("parent_ref_id") or "").strip()
        link = {
            "ref_id": current_ref,
            "sub_action": sub_action,
            "parent_ref_id": parent_ref or None,
            "transform_metadata": desc.get("transform_metadata") if isinstance(desc.get("transform_metadata"), dict) else {},
            "width_height": desc.get("width_height"),
        }
        chain.append(link)

        if sub_action in _UNSUPPORTED_PROJECTION_SUB_ACTIONS:
            return ProjectionContext(
                local_source_ref=local_ref,
                root_source_ref=None,
                local_width_height=local_width_height,
                root_width_height=None,
                projection_available=False,
                projection_unavailable_reason=(
                    f"parent transform {sub_action} does not preserve source-coordinate mapping"
                ),
                projection_chain=chain,
            )

        if sub_action == "zoom":
            meta = link["transform_metadata"]
            has_box = _link_box_norm(link) is not None
            has_factor_only = meta.get("factor_applied") is not None and not has_box
            if not has_box and not has_factor_only:
                return ProjectionContext(
                    local_source_ref=local_ref,
                    root_source_ref=None,
                    local_width_height=local_width_height,
                    root_width_height=None,
                    projection_available=False,
                    projection_unavailable_reason="zoom transform lacks recoverable source-region metadata",
                    projection_chain=chain,
                )

        if sub_action not in {"crop", "zoom", "point_crops_crop"}:
            return ProjectionContext(
                local_source_ref=local_ref,
                root_source_ref=None,
                local_width_height=local_width_height,
                root_width_height=None,
                projection_available=False,
                projection_unavailable_reason=(
                    f"parent transform {sub_action or 'unknown'} does not preserve source-coordinate mapping"
                ),
                projection_chain=chain,
            )

        if not parent_ref:
            return ProjectionContext(
                local_source_ref=local_ref,
                root_source_ref=None,
                local_width_height=local_width_height,
                root_width_height=None,
                projection_available=False,
                projection_unavailable_reason=f"missing parent_ref_id on derived ref {current_ref}",
                projection_chain=chain,
            )
        current_ref = parent_ref

    if not current_ref.startswith(_IMAGE_ASSOC_PREFIX):
        return ProjectionContext(
            local_source_ref=local_ref,
            root_source_ref=None,
            local_width_height=local_width_height,
            root_width_height=None,
            projection_available=False,
            projection_unavailable_reason="projection chain did not terminate at image:assoc:* original source",
            projection_chain=chain,
        )

    root_wh = _root_dimensions(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        root_source_ref=current_ref,
    )
    return ProjectionContext(
        local_source_ref=local_ref,
        root_source_ref=current_ref,
        local_width_height=local_width_height,
        root_width_height=root_wh,
        projection_available=True,
        projection_unavailable_reason=None,
        projection_chain=chain,
    )


_PROJECTION_POINT_KEYS = (
    "local_source_ref",
    "local_source_width_height",
    "local_point_norm",
    "local_box_px",
    "local_box_norm",
    "root_source_ref",
    "root_source_width_height",
    "root_point_norm",
    "root_box_norm",
    "root_box_px",
    "projection_available",
    "projection_unavailable_reason",
    "projection_chain",
)


def enrich_point_geometry_with_projection(
    point: dict[str, Any],
    *,
    projection_ctx: ProjectionContext,
) -> dict[str, Any]:
    """Add local/root projection fields; preserve existing local geometry aliases."""
    local_wh = projection_ctx.local_width_height
    if local_wh is None and isinstance(point.get("source_width_height"), (list, tuple)):
        local_wh = [int(point["source_width_height"][0]), int(point["source_width_height"][1])]

    point["local_source_ref"] = projection_ctx.local_source_ref
    if local_wh is not None:
        point["local_source_width_height"] = list(local_wh)
    point["local_point_norm"] = list(point.get("point_norm") or [])
    point["local_box_px"] = list(point.get("box_px") or [])
    point["local_box_norm"] = list(point.get("box_norm") or [])

    point["projection_chain"] = [
        {
            "ref_id": row.get("ref_id"),
            "sub_action": row.get("sub_action"),
            "parent_ref_id": row.get("parent_ref_id"),
        }
        for row in projection_ctx.projection_chain
    ]

    if projection_ctx.projection_available and projection_ctx.root_source_ref:
        root_pn = compose_point_norm_to_root(point["local_point_norm"], projection_ctx.projection_chain)
        root_bn = compose_box_norm_to_root(point["local_box_norm"], projection_ctx.projection_chain)
        if root_pn is None or root_bn is None:
            point["projection_available"] = False
            point["projection_unavailable_reason"] = "projection chain could not compose local geometry"
            point["root_source_ref"] = projection_ctx.root_source_ref
            return point

        point["projection_available"] = True
        point["projection_unavailable_reason"] = None
        point["root_source_ref"] = projection_ctx.root_source_ref
        if projection_ctx.root_width_height is not None:
            point["root_source_width_height"] = list(projection_ctx.root_width_height)
            rw, rh = projection_ctx.root_width_height
            point["root_box_px"] = [
                int(round(root_bn[0] * rw)),
                int(round(root_bn[1] * rh)),
                int(round(root_bn[2] * rw)),
                int(round(root_bn[3] * rh)),
            ]
        point["root_point_norm"] = root_pn
        point["root_box_norm"] = root_bn
        return point

    point["projection_available"] = False
    point["projection_unavailable_reason"] = projection_ctx.projection_unavailable_reason
    point["root_source_ref"] = projection_ctx.root_source_ref
    return point


def copy_projection_fields(source: dict[str, Any]) -> dict[str, Any]:
    return {key: source[key] for key in _PROJECTION_POINT_KEYS if key in source}
