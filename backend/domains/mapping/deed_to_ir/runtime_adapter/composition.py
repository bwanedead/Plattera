"""Mechanical deed-to-IR to harness composition translation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import is_dataclass
from typing import Any

from harness.runtime.composition import TurnBlock, TurnSurface

from ..domain_pack import DeedToIrDomainPack
from ..payloads import DeedToIrStartupHandoff
from ..prompting import PromptBlock

DEED_TO_IR_RUNTIME_SURFACE_ID = "deed_to_ir"
_PROMPT_BLOCK_NAMESPACE = "deed_to_ir.prompt_block"
_PAYLOAD_NAMESPACE = "deed_to_ir"


def build_deed_to_ir_turn_surface(
    *,
    domain_pack: DeedToIrDomainPack,
    startup_handoff: DeedToIrStartupHandoff,
) -> TurnSurface:
    """Package deed-to-IR prompt blocks and payload; Brief A binds no tools."""
    payload = domain_pack.build_surface_payload()
    tool_bindings: tuple = ()
    bound_tool_ids = [binding.tool_id for binding in tool_bindings]
    if bound_tool_ids != payload["tool_ids"]:
        raise ValueError("deed_to_ir_runtime_tool_binding_mismatch")

    all_blocks = _build_turn_blocks(
        domain_pack.build_runtime_prompt_blocks(startup_handoff=startup_handoff)
    )
    surface_payload = {
        _PAYLOAD_NAMESPACE: _jsonable(payload),
        f"{_PAYLOAD_NAMESPACE}_startup_handoff": _jsonable(_handoff_wire(startup_handoff)),
    }
    return TurnSurface(
        surface_id=DEED_TO_IR_RUNTIME_SURFACE_ID,
        blocks=all_blocks,
        payload=surface_payload,
        tool_bindings=tool_bindings,
    )


def _handoff_wire(handoff: DeedToIrStartupHandoff) -> dict[str, Any]:
    return {
        "scope": {
            "dossier_id": handoff.scope.dossier_id,
            "run_id": handoff.scope.run_id,
            "workspace_id": handoff.scope.workspace_id,
            "transcription_id": handoff.scope.transcription_id,
        },
        "source": {
            "loaded_source_label": handoff.source.loaded_source_label,
            "source_revision_ref": handoff.source.source_revision_ref,
            "published_at": handoff.source.published_at,
        },
        "normalized_or_mapping_transcript": handoff.normalized_or_mapping_transcript,
        "source_transcript_verbatim": handoff.source_transcript_verbatim,
        "issues": list(handoff.issues),
        "hitl_decisions": list(handoff.hitl_decisions),
        "parcel_metadata": dict(handoff.parcel_metadata),
        "evidence_refs": list(handoff.evidence_refs),
        "counts": dict(handoff.counts),
        "excerpts": dict(handoff.excerpts),
    }


def _build_turn_blocks(prompt_blocks: Sequence[PromptBlock]) -> tuple[TurnBlock, ...]:
    return tuple(
        TurnBlock(
            content=block.text,
            metadata={
                _PROMPT_BLOCK_NAMESPACE: {
                    "block_id": block.block_id,
                    "layer": block.layer,
                    "owner": block.owner,
                    "source_path": block.source_path,
                    "version": block.version,
                }
            },
        )
        for block in prompt_blocks
    )


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        from dataclasses import asdict

        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
