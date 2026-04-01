"""Thin transcript-edit pack index—bundles semantic surfaces, no orchestration."""

from __future__ import annotations

from dataclasses import dataclass

from .execution.tool_specs import SemanticToolSpec, build_transcript_edit_tool_specs
from .manifest import TranscriptEditManifest, build_transcript_edit_manifest
from .prompting import (
    PromptBlock,
    build_transcript_edit_branch_blocks,
    build_transcript_edit_procedural_guidance_blocks,
)
from .semantics.closure import TranscriptEditClosureSemantics, transcript_edit_closure_semantics
from .semantics.handoff import TranscriptEditHandoffSemantics, transcript_edit_handoff_semantics


@dataclass(frozen=True)
class TranscriptEditDomainPack:
    """Indexes prompt, tool, closure, and handoff surfaces; state shapes live under ``state/`` (see manifest refs)."""

    manifest: TranscriptEditManifest

    def build_prompt_branch_blocks(self) -> tuple[PromptBlock, ...]:
        return (
            *build_transcript_edit_branch_blocks(),
            *build_transcript_edit_procedural_guidance_blocks(),
        )

    def build_tool_specs(self) -> tuple[SemanticToolSpec, ...]:
        return build_transcript_edit_tool_specs()

    def closure_semantics(self) -> TranscriptEditClosureSemantics:
        return transcript_edit_closure_semantics()

    def handoff_semantics(self) -> TranscriptEditHandoffSemantics:
        return transcript_edit_handoff_semantics()


def build_transcript_edit_domain_pack() -> TranscriptEditDomainPack:
    return TranscriptEditDomainPack(manifest=build_transcript_edit_manifest())
