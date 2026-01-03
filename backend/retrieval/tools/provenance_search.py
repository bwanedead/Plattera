from __future__ import annotations

"""
Provenance retrieval tool wrapper.

Defaults:
- recipe: CANONICAL_STACK
- requires dossier_id (gates if missing)
- limit: 10

Debug schema keys:
tool, lanes, defaults, overrides, gating_errors, notes
"""

from dataclasses import dataclass
from typing import Optional

from ..evidence.models import RetrievalResult
from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters


@dataclass
class ProvenanceSearchTool:
    engine: RetrievalEngine

    def __call__(
        self,
        dossier_id: Optional[str],
        *,
        recipe: str = "CANONICAL_STACK",
        filters: Optional[RetrievalFilters] = None,
        limit: int = 10,
    ) -> RetrievalResult:
        if not dossier_id:
            result = RetrievalResult(query="", cards=[], debug={})
            result.debug.update(
                {
                    "tool": "provenance_search",
                    "lanes": ["provenance"],
                    "defaults": {"recipe": "CANONICAL_STACK", "limit": 10},
                    "overrides": {},
                    "gating_errors": ["provenance_requires_dossier_id"],
                    "notes": [],
                }
            )
            return result
        resolved_filters = _with_dossier_id(filters, dossier_id, recipe)
        result = self.engine.search("", filters=resolved_filters, limit=limit, lanes=["provenance"])

        notes = []
        lane_debug = (result.debug.get("lane_debug") or {}).get("provenance") or {}
        for note in lane_debug.get("notes", []) or []:
            notes.append(note)

        defaults = {"recipe": "CANONICAL_STACK", "limit": 10}
        overrides = {"dossier_id": dossier_id}
        if recipe != "CANONICAL_STACK":
            overrides["recipe"] = recipe
        if limit != 10:
            overrides["limit"] = limit
        if filters is not None:
            overrides["filters"] = True

        result.debug.update(
            {
                "tool": "provenance_search",
                "lanes": ["provenance"],
                "defaults": defaults,
                "overrides": overrides,
                "gating_errors": [],
                "notes": notes,
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
