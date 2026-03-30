"""Thin transcript-edit domain pack shell."""

from __future__ import annotations

from dataclasses import dataclass

from .manifest import TranscriptEditManifest, build_transcript_edit_manifest
from .prompting.branch import PromptBlock, build_transcript_edit_branch_blocks


@dataclass(frozen=True)
class TranscriptEditDomainPack:
    manifest: TranscriptEditManifest

    def build_prompt_branch_blocks(self) -> tuple[PromptBlock, ...]:
        return build_transcript_edit_branch_blocks()


def build_transcript_edit_domain_pack() -> TranscriptEditDomainPack:
    return TranscriptEditDomainPack(manifest=build_transcript_edit_manifest())

