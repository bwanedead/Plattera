"""Deed-to-IR domain edge adapter for generic harness composition surfaces."""

from .adapter import DeedToIrRuntimeAdapter, build_deed_to_ir_runtime_adapter
from .composition import (
    DEED_TO_IR_RUNTIME_SURFACE_ID,
    build_deed_to_ir_turn_surface,
)

__all__ = [
    "DEED_TO_IR_RUNTIME_SURFACE_ID",
    "DeedToIrRuntimeAdapter",
    "build_deed_to_ir_runtime_adapter",
    "build_deed_to_ir_turn_surface",
]
