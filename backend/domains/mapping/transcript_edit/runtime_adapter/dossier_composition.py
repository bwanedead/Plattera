"""Dossier-mode turn-surface composition for transcript-edit."""

from __future__ import annotations

from harness.runtime.composition import TurnSurface
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
)

from ..domain_pack import TranscriptEditDomainPack
from .composition import compose_transcript_edit_turn_surface
from .dossier_tool_bindings import build_dossier_transcript_edit_tool_bindings


def build_dossier_transcript_edit_turn_surface(
    *,
    domain_pack: TranscriptEditDomainPack,
    bundle: DossierStartupInventoryBundle,
) -> TurnSurface:
    """Bind dossier handlers and package them with the dossier inventory surface."""
    if not isinstance(bundle, DossierStartupInventoryBundle):
        raise TypeError("dossier_startup_inventory_bundle_required")
    tool_bindings = build_dossier_transcript_edit_tool_bindings(bundle=bundle)
    return compose_transcript_edit_turn_surface(
        domain_pack=domain_pack,
        startup_inventory=bundle.inventory,
        tool_bindings=tool_bindings,
    )
