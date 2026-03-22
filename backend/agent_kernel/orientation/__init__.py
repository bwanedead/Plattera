"""Generic orientation containers and validation (agent kernel).

Domain-specific adaptation (e.g. transcript-edit checklist seeds) lives under ``agents/<domain>/``.
"""
from __future__ import annotations

from .contract import (
    collect_orientation_startup_input,
    coerce_generic_orientation_payload,
)
from .startup_document import (
    coerce_startup_understanding,
    fallback_decision_key_for_startup_merge,
    startup_understanding_has_minimum_viable,
    work_item_impact_tier,
)

__all__ = [
    "collect_orientation_startup_input",
    "coerce_generic_orientation_payload",
    "coerce_startup_understanding",
    "fallback_decision_key_for_startup_merge",
    "startup_understanding_has_minimum_viable",
    "work_item_impact_tier",
]
