from __future__ import annotations

from enum import Enum

from corpus.types import CorpusEntryKind


class ProvenanceRecipe(str, Enum):
    CANONICAL_STACK = "CANONICAL_STACK"
    FINAL_ONLY = "FINAL_ONLY"
    ARTIFACTS_ONLY = "ARTIFACTS_ONLY"


RECIPE_KINDS: dict[ProvenanceRecipe, tuple[CorpusEntryKind, ...]] = {
    ProvenanceRecipe.FINAL_ONLY: (CorpusEntryKind.FINALIZED_DOSSIER_TEXT,),
    ProvenanceRecipe.ARTIFACTS_ONLY: (
        CorpusEntryKind.SCHEMA_JSON,
        CorpusEntryKind.GEOREF_JSON,
    ),
    ProvenanceRecipe.CANONICAL_STACK: (
        CorpusEntryKind.FINALIZED_DOSSIER_TEXT,
        CorpusEntryKind.SCHEMA_JSON,
        CorpusEntryKind.GEOREF_JSON,
    ),
}


def parse_provenance_recipe(value: str | ProvenanceRecipe) -> ProvenanceRecipe:
    if isinstance(value, ProvenanceRecipe):
        return value
    if not isinstance(value, str):
        raise ValueError(f"Unknown provenance recipe: {value!r}")
    key = value.strip()
    norm = key.replace("-", "_").replace(" ", "_").upper()
    if norm in ProvenanceRecipe.__members__:
        return ProvenanceRecipe[norm]
    for recipe in ProvenanceRecipe:
        if recipe.value == key:
            return recipe
    raise ValueError(f"Unknown provenance recipe: {value!r}")
