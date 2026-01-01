from __future__ import annotations

from enum import Enum


class ProvenanceRecipe(str, Enum):
    CANONICAL_STACK = "CANONICAL_STACK"
    FINAL_ONLY = "FINAL_ONLY"
    ARTIFACTS_ONLY = "ARTIFACTS_ONLY"


def parse_provenance_recipe(value: str | ProvenanceRecipe) -> ProvenanceRecipe:
    if isinstance(value, ProvenanceRecipe):
        return value
    key = value.strip()
    if key in ProvenanceRecipe.__members__:
        return ProvenanceRecipe[key]
    upper = key.upper()
    if upper in ProvenanceRecipe.__members__:
        return ProvenanceRecipe[upper]
    for recipe in ProvenanceRecipe:
        if recipe.value == key:
            return recipe
    raise ValueError(f"Unknown provenance recipe: {value!r}")
