"""Thin deed-to-IR pack index — bundles semantic surfaces, no orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from domains.mapping.prompting.family_branch import build_mapping_family_branch_blocks
from .execution.tool_specs import SemanticToolSpec, build_deed_to_ir_tool_specs
from .manifest import DeedToIrManifest, build_deed_to_ir_manifest
from .payloads import DeedToIrStartupHandoff
from .prompting import (
    PromptBlock,
    build_deed_to_ir_branch_blocks,
    build_deed_to_ir_feature_graph_authoring_guide_blocks,
    build_deed_to_ir_procedural_guidance_blocks,
)
from .prompting.surfaces.startup_context import build_startup_context_block
from .semantics.closure import DeedToIrClosureSemantics, deed_to_ir_closure_semantics
from .semantics.handoff import DeedToIrHandoffSemantics, deed_to_ir_handoff_semantics


@dataclass(frozen=True)
class DeedToIrDomainPack:
    manifest: DeedToIrManifest

    def build_semantic_prompt_blocks(self) -> tuple[PromptBlock, ...]:
        return (
            *build_mapping_family_branch_blocks(),
            *build_deed_to_ir_branch_blocks(),
            *build_deed_to_ir_feature_graph_authoring_guide_blocks(),
            *build_deed_to_ir_procedural_guidance_blocks(),
        )

    def build_runtime_prompt_blocks(
        self,
        *,
        startup_handoff: DeedToIrStartupHandoff,
    ) -> tuple[PromptBlock, ...]:
        return (
            *self.build_semantic_prompt_blocks(),
            build_startup_context_block(startup_handoff),
        )

    def build_tool_specs(self) -> tuple[SemanticToolSpec, ...]:
        return build_deed_to_ir_tool_specs()

    def build_surface_payload(self) -> dict[str, Any]:
        tool_specs = self.build_tool_specs()
        declared_tool_ids = self.manifest.declared_semantic_tool_ids
        spec_tool_ids = tuple(spec.tool_id for spec in tool_specs)
        if spec_tool_ids != declared_tool_ids:
            raise ValueError("deed_to_ir_declared_tool_ids_drift")
        return _jsonable(
            {
                "tool_specs": [asdict(spec) for spec in tool_specs],
                "tool_ids": list(declared_tool_ids),
                "closure_policy": asdict(self.manifest.closure_policy),
            }
        )

    def closure_semantics(self) -> DeedToIrClosureSemantics:
        return deed_to_ir_closure_semantics()

    def handoff_semantics(self) -> DeedToIrHandoffSemantics:
        return deed_to_ir_handoff_semantics()


def build_deed_to_ir_domain_pack() -> DeedToIrDomainPack:
    return DeedToIrDomainPack(manifest=build_deed_to_ir_manifest())


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
