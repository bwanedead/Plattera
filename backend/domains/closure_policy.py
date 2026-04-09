"""Generic domain-owned closure policy contracts.

The harness may enforce these mechanically, but domains define the dimensions,
questions, and when enforcement should be active.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ClosureDimensionStandard:
    dimension_id: str
    title: str
    question: str
    guidance: str | None = None


@dataclass(frozen=True)
class DomainClosurePolicy:
    hard_enforced: bool = False
    enforce_on_publish: bool = False
    enforce_on_complete: bool = False
    minimum_resolution_items_for_save: int = 0
    minimum_resolution_items_for_wait: int = 0
    minimum_resolution_items_for_publish: int = 0
    minimum_resolution_items_for_complete: int = 0
    required_dimension_ids: tuple[str, ...] = ()
    standards: tuple[ClosureDimensionStandard, ...] = ()
