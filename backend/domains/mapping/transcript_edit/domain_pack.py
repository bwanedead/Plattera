"""Thin transcript-edit pack index—bundles semantic surfaces, no orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from domains.mapping.prompting.family_branch import build_mapping_family_branch_blocks
from .execution.dossier_tool_specs import build_dossier_transcript_edit_tool_specs
from .execution.subtask_profiles import build_transcript_edit_subtask_profiles
from .execution.tool_specs import SemanticToolSpec, build_transcript_edit_tool_specs
from .manifest import TranscriptEditManifest, build_transcript_edit_manifest
from .payloads import DossierTranscriptEditStartupInventory, TranscriptEditStartupInventory
from .prompting import (
    PromptBlock,
    build_transcript_edit_branch_blocks,
    build_transcript_edit_dossier_guidance_block,
    build_transcript_edit_procedural_guidance_blocks,
)
from .prompting.surfaces.startup_context import build_startup_context_block
from .semantics.closure import TranscriptEditClosureSemantics, transcript_edit_closure_semantics
from .semantics.handoff import TranscriptEditHandoffSemantics, transcript_edit_handoff_semantics


@dataclass(frozen=True)
class TranscriptEditDomainPack:
    """Indexes prompt, tool, closure, and handoff surfaces; state shapes live under ``state/`` (see manifest refs)."""

    manifest: TranscriptEditManifest

    def build_semantic_prompt_blocks(self) -> tuple[PromptBlock, ...]:
        return (
            *build_mapping_family_branch_blocks(),
            *build_transcript_edit_branch_blocks(),
            *build_transcript_edit_procedural_guidance_blocks(),
        )

    def build_runtime_prompt_blocks(
        self,
        *,
        startup_inventory: (
            TranscriptEditStartupInventory | DossierTranscriptEditStartupInventory
        ),
    ) -> tuple[PromptBlock, ...]:
        blocks = list(self.build_semantic_prompt_blocks())
        if isinstance(startup_inventory, DossierTranscriptEditStartupInventory):
            blocks.append(build_transcript_edit_dossier_guidance_block())
        blocks.append(build_startup_context_block(startup_inventory))
        return tuple(blocks)

    def build_tool_specs(
        self,
        *,
        startup_inventory: (
            TranscriptEditStartupInventory | DossierTranscriptEditStartupInventory | None
        ) = None,
    ) -> tuple[SemanticToolSpec, ...]:
        if isinstance(startup_inventory, DossierTranscriptEditStartupInventory):
            return build_dossier_transcript_edit_tool_specs()
        return build_transcript_edit_tool_specs()

    def build_surface_payload(
        self,
        *,
        startup_inventory: (
            TranscriptEditStartupInventory | DossierTranscriptEditStartupInventory | None
        ) = None,
    ) -> dict[str, Any]:
        tool_specs = self.build_tool_specs(startup_inventory=startup_inventory)
        declared_tool_ids = self.manifest.declared_semantic_tool_ids
        spec_tool_ids = tuple(spec.tool_id for spec in tool_specs)
        if spec_tool_ids != declared_tool_ids:
            raise ValueError("transcript_edit_declared_tool_ids_drift")
        return _jsonable(
            {
                "tool_specs": [asdict(spec) for spec in tool_specs],
                "tool_ids": list(declared_tool_ids),
                "closure_policy": asdict(self.manifest.closure_policy),
                "subtask_profiles": list(build_transcript_edit_subtask_profiles()),
            }
        )

    def closure_semantics(self) -> TranscriptEditClosureSemantics:
        return transcript_edit_closure_semantics()

    def handoff_semantics(self) -> TranscriptEditHandoffSemantics:
        return transcript_edit_handoff_semantics()


def build_transcript_edit_domain_pack() -> TranscriptEditDomainPack:
    return TranscriptEditDomainPack(manifest=build_transcript_edit_manifest())


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
