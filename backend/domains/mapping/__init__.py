"""Mapping-family domain packs and adapter registrations."""

from __future__ import annotations

from domains.registry import DomainAdapterRegistration, DomainAdapterRegistry

_TRANSCRIPT_EDIT_DOMAIN_ID = "transcript_edit"
_DEED_TO_IR_DOMAIN_ID = "deed_to_ir"


def build_mapping_domain_adapter_registry() -> DomainAdapterRegistry:
    """Register mapping-family domain adapters by opaque domain id only."""

    registry = DomainAdapterRegistry()
    registry.register(
        DomainAdapterRegistration(
            domain_id=_TRANSCRIPT_EDIT_DOMAIN_ID,
            adapter_factory=_build_transcript_edit_runtime_adapter,
        )
    )
    registry.register(
        DomainAdapterRegistration(
            domain_id=_DEED_TO_IR_DOMAIN_ID,
            adapter_factory=_build_deed_to_ir_runtime_adapter,
        )
    )
    return registry


def _build_transcript_edit_runtime_adapter():
    from .transcript_edit.runtime_adapter import build_transcript_edit_runtime_adapter

    return build_transcript_edit_runtime_adapter()


def _build_deed_to_ir_runtime_adapter():
    from .deed_to_ir.runtime_adapter import build_deed_to_ir_runtime_adapter

    return build_deed_to_ir_runtime_adapter()


__all__ = [
    "build_mapping_domain_adapter_registry",
]
