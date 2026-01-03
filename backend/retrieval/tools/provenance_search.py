from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..evidence.models import RetrievalResult
from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..lanes.provenance.recipes import parse_provenance_recipe


@dataclass
class ProvenanceSearchTool:
    engine: RetrievalEngine

    # Defaults:
    # - recipe: CANONICAL_STACK
    # - requires dossier_id (returns empty + debug error if missing)
    def __call__(
        self,
        dossier_id: Optional[str],
        *,
        recipe: str = "CANONICAL_STACK",
        filters: Optional[RetrievalFilters] = None,
        limit: int = 10,
    ) -> RetrievalResult:
        parsed = parse_provenance_recipe(recipe)
        if not dossier_id:
            result = RetrievalResult(query="", cards=[], debug={})
            result.debug.update(
                {
                    "tool": "ProvenanceSearchTool",
                    "tool_recipe": parsed.value,
                    "tool_lanes": ["provenance"],
                    "error": "provenance_requires_dossier_id",
                }
            )
            return result
        resolved_filters = _with_dossier_id(filters, dossier_id, parsed.value)
        result = self.engine.search("", filters=resolved_filters, limit=limit, lanes=["provenance"])
        result.debug.update(
            {
                "tool": "ProvenanceSearchTool",
                "tool_recipe": parsed.value,
                "tool_lanes": ["provenance"],
                "tool_dossier_id": dossier_id,
            }
        )
        return result


def _with_dossier_id(
    filters: Optional[RetrievalFilters], dossier_id: str, recipe: str
) -> RetrievalFilters:
    base_extra = dict(filters.extra or {}) if filters else {}
    base_extra["provenance_recipe"] = recipe
    if not filters:
        return RetrievalFilters(dossier_id=dossier_id, extra=base_extra)
    return RetrievalFilters(
        view=filters.view,
        dossier_id=dossier_id,
        transcription_id=filters.transcription_id,
        artifact_type=filters.artifact_type,
        since_iso=filters.since_iso,
        until_iso=filters.until_iso,
        extra=base_extra,
    )
