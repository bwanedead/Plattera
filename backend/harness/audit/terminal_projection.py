"""Canonical mechanical terminal projection for audit artifacts.

One projection feeds ``index.json``, ``review.md``, and ``timeline.md``.
Native finalization and outer-lifecycle reclassification share this shape;
only ``projection_kind`` distinguishes them for rendering.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

PROJECTION_KIND_NATIVE = "native"
PROJECTION_KIND_OVERRIDE = "override"
ALLOWED_PROJECTION_KINDS = frozenset({PROJECTION_KIND_NATIVE, PROJECTION_KIND_OVERRIDE})
CANONICAL_PROJECTION_FIELDS = (
    "projection_kind",
    "terminal_class",
    "reason_code",
    "iterations",
    "latest_refs",
    "terminal_decision",
)


def build_terminal_projection(
    *,
    projection_kind: str,
    terminal_class: str,
    reason_code: str,
    iterations: int,
    latest_refs: Mapping[str, Any] | None = None,
    terminal_decision: str | None = None,
) -> dict[str, Any]:
    kind = str(projection_kind or "").strip()
    if kind not in ALLOWED_PROJECTION_KINDS:
        raise ValueError(
            "projection_kind must be exactly "
            f"{PROJECTION_KIND_NATIVE!r} or {PROJECTION_KIND_OVERRIDE!r}"
        )
    return {
        "projection_kind": kind,
        "terminal_class": str(terminal_class or ""),
        "reason_code": str(reason_code or ""),
        "iterations": int(iterations),
        "latest_refs": dict(latest_refs or {}),
        "terminal_decision": terminal_decision,
    }


def highest_retained_turn_index(turns: list[Mapping[str, Any]] | None) -> int:
    highest = 0
    for turn in turns or []:
        try:
            idx = int(turn.get("turn_index") or 0)
        except (TypeError, ValueError):
            continue
        if idx > highest:
            highest = idx
    return highest


def effective_iterations(
    caller_iterations: int,
    turns: list[Mapping[str, Any]] | None,
) -> int:
    """Mechanical iteration count: caller value vs highest retained turn index."""
    try:
        provided = int(caller_iterations)
    except (TypeError, ValueError):
        provided = 0
    return max(provided, highest_retained_turn_index(turns))


def is_override_projection(projection: Mapping[str, Any] | None) -> bool:
    if not isinstance(projection, Mapping):
        return False
    return str(projection.get("projection_kind") or "") == PROJECTION_KIND_OVERRIDE


def render_run_level_override_section(
    projection: Mapping[str, Any] | None,
    *,
    fence_values: bool = False,
) -> list[str]:
    """Render the explicit reclassification section, or nothing for native outcomes."""
    if not is_override_projection(projection):
        return []
    assert projection is not None

    def _fmt(value: Any) -> str:
        text = str(value or "unknown")
        return f"`{text}`" if fence_values else text

    return [
        "## Run-Level Terminal Override",
        "",
        f"- terminal_class: {_fmt(projection.get('terminal_class'))}",
        f"- reason_code: {_fmt(projection.get('reason_code'))}",
        f"- terminal_decision: {_fmt(projection.get('terminal_decision'))}",
        "",
    ]
