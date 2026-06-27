"""Deed-to-IR prompt surface blocks."""

from .feature_graph_authoring_guide import build_deed_to_ir_feature_graph_authoring_guide_blocks
from .procedural_guidance import build_deed_to_ir_procedural_guidance_blocks
from .startup_context import build_startup_context_block

__all__ = [
    "build_deed_to_ir_feature_graph_authoring_guide_blocks",
    "build_deed_to_ir_procedural_guidance_blocks",
    "build_startup_context_block",
]
