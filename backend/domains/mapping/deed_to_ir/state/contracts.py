"""Canonical semantic state shapes for deed-to-IR (skeleton; no IR authoring yet)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IrScopeInventoryRow:
    """One scoped unit inherited from transcript-edit parcel metadata (copy-only orientation)."""

    scope_id: str
    forwardable: bool | None = None
    forwardable_scope: str | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DeedToIrSemanticState:
    """Domain-local semantic bundle for deed-to-IR (authoritative for this pack)."""

    scope_inventory: tuple[IrScopeInventoryRow, ...] = ()
    transcript_edit_source_revision_ref: str | None = None
    ir_artifact_ref: str | None = None
