"""Deed-to-IR domain manifest.

This is the explicit identity surface for the deed pack.
"""

from __future__ import annotations

from domains.common.domain_pack_contracts import DomainManifest

from .capabilities import build_deed_to_ir_capability_requirements
from .handoff import build_deed_to_ir_supported_handoffs


def build_deed_to_ir_domain_manifest() -> DomainManifest:
    """Return the deed-to-IR manifest."""

    return DomainManifest(
        domain_id="deed_to_ir",
        family_id="mapping",
        display_name="Deed to IR",
        capability_requirements=build_deed_to_ir_capability_requirements(),
        supported_handoffs=build_deed_to_ir_supported_handoffs(),
        compatibility_status="compatible",
    )


