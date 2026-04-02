"""Default mechanical turn composer.

This module must stay blind to domain semantics. It only preserves surface
order, copies opaque payloads by surface id, and indexes tool handlers by opaque
tool id.
"""

from __future__ import annotations

from typing import Any

from .contracts import ComposedTurnInput, ToolHandler, TurnBlock, TurnSurface


class DefaultTurnComposer:
    def compose(self, *surfaces: TurnSurface) -> ComposedTurnInput:
        blocks: list[TurnBlock] = []
        surface_payloads: dict[str, dict[str, Any]] = {}
        tool_handlers: dict[str, ToolHandler] = {}

        for surface in surfaces:
            surface_id = _normalize_surface_id(surface.surface_id)
            if surface_id in surface_payloads:
                raise ValueError(f"duplicate_surface_id:{surface_id}")

            blocks.extend(surface.blocks)
            surface_payloads[surface_id] = dict(surface.payload)

            for binding in surface.tool_bindings:
                tool_id = _normalize_tool_id(binding.tool_id)
                if tool_id in tool_handlers:
                    raise ValueError(f"duplicate_tool_id:{tool_id}")
                tool_handlers[tool_id] = binding.handler

        return ComposedTurnInput(
            blocks=tuple(blocks),
            surface_payloads=surface_payloads,
            tool_handlers=tool_handlers,
        )


def _normalize_surface_id(raw: object) -> str:
    surface_id = str(raw or "").strip()
    if not surface_id:
        raise ValueError("surface_id_required")
    return surface_id


def _normalize_tool_id(raw: object) -> str:
    tool_id = str(raw or "").strip()
    if not tool_id:
        raise ValueError("tool_id_required")
    return tool_id
