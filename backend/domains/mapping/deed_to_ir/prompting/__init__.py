"""Deed-to-IR prompt sources."""

from domains.prompting import PromptBlock

from .branch import build_deed_to_ir_branch_blocks
from .surfaces import (
    build_deed_to_ir_feature_graph_authoring_guide_blocks,
    build_deed_to_ir_procedural_guidance_blocks,
)

__all__ = [
    "PromptBlock",
    "build_deed_to_ir_branch_blocks",
    "build_deed_to_ir_feature_graph_authoring_guide_blocks",
    "build_deed_to_ir_procedural_guidance_blocks",
]
