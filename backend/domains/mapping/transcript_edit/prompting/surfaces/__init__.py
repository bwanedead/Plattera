"""Additional authored prompt surfaces for transcript_edit."""

from domains.prompting import PromptBlock

from .procedural_guidance import build_transcript_edit_procedural_guidance_blocks

__all__ = [
    "PromptBlock",
    "build_transcript_edit_procedural_guidance_blocks",
]
