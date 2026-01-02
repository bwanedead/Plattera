from __future__ import annotations

import pytest

from .recipes import ProvenanceRecipe, parse_provenance_recipe


def test_parse_provenance_recipe_enum_passthrough() -> None:
    assert parse_provenance_recipe(ProvenanceRecipe.CANONICAL_STACK) is ProvenanceRecipe.CANONICAL_STACK


@pytest.mark.parametrize(
    "value, expected",
    [
        ("CANONICAL_STACK", ProvenanceRecipe.CANONICAL_STACK),
        ("canonical_stack", ProvenanceRecipe.CANONICAL_STACK),
        ("canonical-stack", ProvenanceRecipe.CANONICAL_STACK),
        ("canonical stack", ProvenanceRecipe.CANONICAL_STACK),
        ("FINAL_ONLY", ProvenanceRecipe.FINAL_ONLY),
        ("artifacts_only", ProvenanceRecipe.ARTIFACTS_ONLY),
    ],
)
def test_parse_provenance_recipe_variants(value: str, expected: ProvenanceRecipe) -> None:
    assert parse_provenance_recipe(value) is expected


def test_parse_provenance_recipe_unknown_raises() -> None:
    with pytest.raises(ValueError):
        parse_provenance_recipe("unknown")
