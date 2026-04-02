"""Mechanical turn-composition contracts only.

If a rule needs domain meaning, semantic ranking, or workflow doctrine, it does
not belong here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping


ToolHandler = Callable[[Any], Any]


@dataclass(frozen=True)
class TurnBlock:
    content: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolBinding:
    tool_id: str
    handler: ToolHandler


@dataclass(frozen=True)
class TurnSurface:
    surface_id: str
    blocks: tuple[TurnBlock, ...] = ()
    payload: Mapping[str, Any] = field(default_factory=dict)
    tool_bindings: tuple[ToolBinding, ...] = ()


@dataclass(frozen=True)
class ComposedTurnInput:
    blocks: tuple[TurnBlock, ...]
    surface_payloads: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_handlers: dict[str, ToolHandler] = field(default_factory=dict)

    def get_tool_handler(self, tool_id: str) -> ToolHandler | None:
        normalized = str(tool_id or "").strip()
        if not normalized:
            return None
        return self.tool_handlers.get(normalized)
