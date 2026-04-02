"""Mechanical turn composition for harness runtime surfaces only.

Keep domain meaning, ranking, closure, and workflow doctrine out of this
package. It only orders blocks, namespaces opaque payloads, and binds tool ids
to handlers.
"""

from __future__ import annotations

from .composer import DefaultTurnComposer
from .contracts import ComposedTurnInput, ToolBinding, ToolHandler, TurnBlock, TurnSurface

__all__ = [
    "ComposedTurnInput",
    "DefaultTurnComposer",
    "ToolBinding",
    "ToolHandler",
    "TurnBlock",
    "TurnSurface",
]
