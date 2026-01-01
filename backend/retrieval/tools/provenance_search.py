from __future__ import annotations

from dataclasses import dataclass, field

from ..evidence.models import RetrievalResult
from ..lanes.provenance.lane import ProvenanceLane
from ..lanes.provenance.recipes import ProvenanceRecipe, parse_provenance_recipe


@dataclass
class ProvenanceSearchTool:
    lane: ProvenanceLane = field(default_factory=ProvenanceLane)

    def __call__(self, dossier_id: str, *, recipe: str = "CANONICAL_STACK") -> RetrievalResult:
        parsed = parse_provenance_recipe(recipe)
        return self.lane.search(dossier_id, recipe=parsed)
