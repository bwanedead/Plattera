"""Mechanical transcript-edit to harness composition translation.

This seam is intentionally narrow: it packages authored prompt blocks,
opaque startup inventory payloads, and tool-id bindings into generic harness
turn surfaces without taking on orchestration or closure semantics.
"""

from __future__ import annotations

from dataclasses import asdict
from collections.abc import Mapping
from typing import Any, Callable, Sequence

from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from tooling.mapping.transcript_edit import (
    build_transcript_edit_startup_inventory,
    hydrate_source_image_context,
    hydrate_t0_draft_refs,
    hydrate_transcript_edit_working_draft,
)

from ..payloads import TranscriptEditStartupInventory
from ..prompting import PromptBlock

TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID = "transcript_edit"
_PROMPT_BLOCK_NAMESPACE = "transcript_edit.prompt_block"
_PAYLOAD_NAMESPACE = "transcript_edit"


def _tool_handler_passthrough(tool_fn: Callable[..., Any]) -> Callable[[Any], Any]:
    def handler(request: Any) -> Any:
        if not isinstance(request, Mapping):
            raise TypeError("tool_request_must_be_mapping")
        return tool_fn(**dict(request))

    return handler


def _tool_handler_specs() -> tuple[tuple[str, Callable[..., Any]], ...]:
    return (
        ("load_transcript_edit_startup_inventory", build_transcript_edit_startup_inventory),
        ("hydrate_t0_draft_refs", hydrate_t0_draft_refs),
        ("hydrate_transcript_edit_working_draft", hydrate_transcript_edit_working_draft),
        ("load_source_image_context", hydrate_source_image_context),
    )


def _build_turn_blocks(prompt_blocks: Sequence[PromptBlock]) -> tuple[TurnBlock, ...]:
    return tuple(
        TurnBlock(
            content=block.text,
            metadata={
                _PROMPT_BLOCK_NAMESPACE: asdict(block),
            },
        )
        for block in prompt_blocks
    )


def build_transcript_edit_tool_bindings() -> tuple[ToolBinding, ...]:
    """Bind implemented transcript-edit tooling by opaque tool id only."""

    return tuple(
        ToolBinding(tool_id=tool_id, handler=_tool_handler_passthrough(tool_fn))
        for tool_id, tool_fn in _tool_handler_specs()
    )


def build_transcript_edit_turn_surface(
    *,
    prompt_blocks: Sequence[PromptBlock],
    startup_inventory: TranscriptEditStartupInventory,
) -> TurnSurface:
    """Package transcript-edit prompt blocks, inventory payload, and bindings."""

    return TurnSurface(
        surface_id=TRANSCRIPT_EDIT_RUNTIME_SURFACE_ID,
        blocks=_build_turn_blocks(prompt_blocks),
        payload={
            _PAYLOAD_NAMESPACE: {
                "startup_inventory": asdict(startup_inventory),
            },
        },
        tool_bindings=build_transcript_edit_tool_bindings(),
    )
