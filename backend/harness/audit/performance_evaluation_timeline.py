"""Audit timeline rendering for generic performance evaluation metrics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def render_performance_evaluation_timeline(turn: Mapping[str, Any]) -> list[str]:
    """Render a compact timeline section; fails soft when metrics are absent."""
    summary = _coerce_mapping(turn.get("prompt_observability_summary"))
    metrics = _coerce_mapping(summary.get("performance_evaluation"))
    if not metrics:
        return []

    lines = ["Performance evaluation:"]
    accuracy = metrics.get("accuracy_status")
    if accuracy:
        lines.append(f"- accuracy: {str(accuracy).replace('_', ' ')}")

    work_graph = _coerce_mapping(metrics.get("work_graph"))
    if work_graph:
        total = work_graph.get("work_units_total")
        closed = work_graph.get("closed_units")
        open_units = work_graph.get("open_units")
        blocked = work_graph.get("blocked_units")
        if total is not None:
            parts = [f"{total} total"]
            if closed is not None:
                parts.append(f"{closed} closed")
            if open_units is not None:
                parts.append(f"{open_units} open")
            if blocked is not None:
                parts.append(f"{blocked} blocked")
            lines.append(f"- work graph: {' / '.join(parts)}")

    productivity = _coerce_mapping(metrics.get("productivity"))
    if productivity:
        parts: list[str] = []
        if productivity.get("determinations_changed_total") is not None:
            parts.append(f"{productivity['determinations_changed_total']} determinations")
        if productivity.get("units_closed_total") is not None:
            parts.append(f"{productivity['units_closed_total']} closures")
        if productivity.get("determinations_per_turn") is not None:
            parts.append(f"{productivity['determinations_per_turn']} determinations/turn")
        if productivity.get("units_closed_per_turn") is not None:
            parts.append(f"{productivity['units_closed_per_turn']} closures/turn")
        if parts:
            lines.append(f"- productivity: {', '.join(parts)}")

    delegate_yield = _coerce_mapping(metrics.get("delegate_yield"))
    if delegate_yield:
        parts = []
        if delegate_yield.get("delegates_total") is not None:
            parts.append(f"{delegate_yield['delegates_total']} delegates")
        if delegate_yield.get("determinations_per_delegate") is not None:
            parts.append(f"{delegate_yield['determinations_per_delegate']} determinations/delegate")
        if delegate_yield.get("delegates_since_last_determination") is not None:
            parts.append(
                f"{delegate_yield['delegates_since_last_determination']} delegates since last determination"
            )
        if parts:
            lines.append(f"- delegate yield: {', '.join(parts)}")

    input_chars = _coerce_mapping(metrics.get("input_chars"))
    if input_chars:
        parts = []
        if input_chars.get("last_turn") is not None:
            parts.append(f"last {int(input_chars['last_turn']):,}")
        if input_chars.get("cumulative") is not None:
            parts.append(f"cumulative {int(input_chars['cumulative']):,}")
        growth = input_chars.get("growth_last_turn")
        if growth is not None:
            sign = "+" if int(growth) >= 0 else ""
            parts.append(f"growth {sign}{int(growth):,}")
        if input_chars.get("max_turn") is not None:
            parts.append(f"max {int(input_chars['max_turn']):,}")
        if parts:
            lines.append(f"- input chars: {' / '.join(parts)}")

    turns = _coerce_mapping(metrics.get("turns"))
    if turns:
        parts = []
        if turns.get("wall_seconds_last_turn") is not None:
            parts.append(f"last {float(turns['wall_seconds_last_turn']):.1f}s")
        if turns.get("wall_seconds_total") is not None:
            parts.append(f"total {_format_wall_duration(float(turns['wall_seconds_total']))}")
        if turns.get("avg_wall_seconds_last_5") is not None:
            parts.append(f"avg last 5 {float(turns['avg_wall_seconds_last_5']):.1f}s")
        if parts:
            lines.append(f"- wall time: {' / '.join(parts)}")

    pressure = metrics.get("current_pressure")
    if isinstance(pressure, list) and pressure:
        lines.append(f"- pressure: {'; '.join(str(flag) for flag in pressure)}")

    lines.append("")
    return lines


def _coerce_mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _format_wall_duration(seconds: float) -> str:
    total = int(round(seconds))
    minutes, sec = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes}m{sec}s"
    if minutes:
        return f"{minutes}m{sec}s"
    return f"{sec}s"
