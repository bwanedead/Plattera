"""Compatibility re-export for the transcript-edit orientation tool (lazy).

**Canonical definition and implementation:** ``agents.transcript_edit.orient_tool.TranscriptOrientBaselineTool``.

This module exists so older imports keep working without pulling domain code during
``agent_kernel.tooling`` load. Prefer importing from ``orient_tool`` directly in new code.

Generic orientation containers: ``agent_kernel.orientation``. Domain prompts/checklist adapters:
``agents.transcript_edit`` (Phase 30 seam).
"""

from __future__ import annotations

from typing import Any

__all__ = ["TranscriptOrientBaselineTool"]


def __getattr__(name: str) -> Any:
    if name == "TranscriptOrientBaselineTool":
        from agents.transcript_edit.orient_tool import TranscriptOrientBaselineTool as _Cls

        return _Cls
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
