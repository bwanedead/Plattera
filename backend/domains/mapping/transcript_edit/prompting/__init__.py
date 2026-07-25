"""Transcript-edit prompt sources."""

from domains.prompting import PromptBlock

from .branch import build_transcript_edit_branch_blocks
from .surfaces import (
    build_transcript_edit_dossier_guidance_block,
    build_transcript_edit_procedural_guidance_blocks,
)

__all__ = [
    "PromptBlock",
    "build_transcript_edit_branch_blocks",
    "build_transcript_edit_dossier_guidance_block",
    "build_transcript_edit_procedural_guidance_blocks",
]
