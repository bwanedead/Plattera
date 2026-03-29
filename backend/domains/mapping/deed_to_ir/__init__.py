"""Deed-to-IR prompt and identity surfaces."""

from .bundle import build_deed_to_ir_domain_pack_bundle
from .capabilities import build_deed_to_ir_capability_requirements
from .handoff import build_deed_to_ir_supported_handoffs
from .manifest import build_deed_to_ir_domain_manifest
from .prompt_sources import build_deed_to_ir_branch_blocks

__all__ = [
    "build_deed_to_ir_branch_blocks",
    "build_deed_to_ir_capability_requirements",
    "build_deed_to_ir_domain_manifest",
    "build_deed_to_ir_domain_pack_bundle",
    "build_deed_to_ir_supported_handoffs",
]
