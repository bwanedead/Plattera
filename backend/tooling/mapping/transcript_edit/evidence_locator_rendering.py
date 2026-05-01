"""Generic rendering helpers for agent-authored evidence locators.

The helpers here translate already-authored locator coordinates into drawing
instructions. They do not infer regions, extract claims, or interpret domain
content.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SUPPORTED_RENDERED_LOCATOR_KINDS = frozenset({"image_region"})
SUMMARY_ONLY_LOCATOR_KINDS = frozenset(
    {"text_span", "log_span", "code_span", "table_cell", "json_path"}
)


def build_locator_render_plan(
    *,
    source_ref: str,
    locators: list[Any],
    image_width: int,
    image_height: int,
) -> dict[str, Any]:
    """Return deterministic annotation params plus per-locator summaries."""

    annotations: list[dict[str, Any]] = []
    rendered_locators: list[dict[str, Any]] = []
    summary_only_locators: list[dict[str, Any]] = []
    unsupported_locators: list[dict[str, Any]] = []

    for index, raw in enumerate(locators):
        if not isinstance(raw, Mapping):
            unsupported_locators.append(_unsupported(index, None, None, "locator_not_object"))
            continue
        locator = dict(raw)
        locator_kind = str(locator.get("locator_kind") or "").strip()
        ref_id = str(locator.get("ref_id") or "").strip()
        label = str(locator.get("label") or f"locator-{index + 1}").strip()
        if ref_id and ref_id != source_ref:
            unsupported_locators.append(_unsupported(index, ref_id, locator_kind, "ref_id_mismatch", label=label))
            continue
        if locator_kind == "image_region":
            box_norm = locator.get("box_norm")
            box = _box_norm_to_pixels(box_norm, image_width=image_width, image_height=image_height)
            if box is None:
                unsupported_locators.append(_unsupported(index, ref_id or source_ref, locator_kind, "box_norm_invalid", label=label))
                continue
            annotations.extend(
                (
                    {"type": "highlight", "box": box, "color": [255, 235, 59], "alpha": 90},
                    {"type": "bbox", "box": box, "color": [255, 0, 0], "width": 3},
                    {"type": "label", "box": box, "text": label, "color": [255, 0, 0]},
                )
            )
            rendered_locators.append(
                {
                    "locator_index": index,
                    "source_ref": ref_id or source_ref,
                    "locator_kind": locator_kind,
                    "label": label,
                    "box_norm": list(box_norm) if isinstance(box_norm, list) else box_norm,
                    "box": box,
                }
            )
            continue
        if locator_kind in SUMMARY_ONLY_LOCATOR_KINDS:
            summary = summarize_locator(locator, index=index)
            summary["reason"] = "summary_only"
            summary_only_locators.append(summary)
        else:
            unsupported_locators.append(
                _unsupported(index, ref_id or source_ref, locator_kind, "unsupported_locator_kind", label=label)
            )

    return {
        "annotations": annotations,
        "rendered_locators": rendered_locators,
        "summary_only_locators": summary_only_locators,
        "unsupported_locators": unsupported_locators,
    }


def summarize_locator(locator: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    """Bounded audit/result summary for any locator kind."""

    keys = (
        "ref_id",
        "locator_kind",
        "target",
        "label",
        "box_norm",
        "line_start",
        "line_end",
        "char_start",
        "char_end",
        "row",
        "column",
        "json_path",
    )
    out = {"locator_index": index}
    for key in keys:
        value = locator.get(key)
        if value is not None and value != "":
            out[key] = value
    return out


def _unsupported(
    index: int,
    ref_id: str | None,
    locator_kind: str | None,
    reason: str,
    *,
    label: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "locator_index": index,
        "ref_id": ref_id,
        "locator_kind": locator_kind or "unknown",
        "reason": reason,
    }
    if label:
        out["label"] = label
    return out


def _box_norm_to_pixels(
    box_norm: Any,
    *,
    image_width: int,
    image_height: int,
) -> list[int] | None:
    if not isinstance(box_norm, list) or len(box_norm) != 4:
        return None
    try:
        x_min, y_min, x_max, y_max = [float(value) for value in box_norm]
    except (TypeError, ValueError):
        return None
    if not (0.0 <= x_min < x_max <= 1.0 and 0.0 <= y_min < y_max <= 1.0):
        return None
    return [
        max(0, min(image_width, int(round(x_min * image_width)))),
        max(0, min(image_height, int(round(y_min * image_height)))),
        max(0, min(image_width, int(round(x_max * image_width)))),
        max(0, min(image_height, int(round(y_max * image_height)))),
    ]
