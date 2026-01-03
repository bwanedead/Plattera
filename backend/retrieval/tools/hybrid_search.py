from __future__ import annotations

"""
Hybrid retrieval tool wrapper (lexical -> provenance orchestration).

Defaults:
- uses engine hybrid orchestration ("hybrid" lane)
- limit: 10

Debug schema keys:
tool, lanes, defaults, overrides, gating_errors, notes
"""

from dataclasses import dataclass
from typing import Optional

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class HybridSearchTool:
    engine: RetrievalEngine

    def __call__(self, query: str, *, filters: Optional[RetrievalFilters] = None, limit: int = 10) -> RetrievalResult:
        result = self.engine.search(query, filters=filters, limit=limit, lanes=["hybrid"])
        notes = []
        engine_defaults = {
            "lexical_internal_limit": self.engine.hybrid_config.lexical_internal_limit,
            "max_anchor_dossiers": self.engine.hybrid_config.max_anchor_dossiers,
            "provenance_recipe": self.engine.hybrid_config.provenance_recipe.value,
        }
        notes.append("engine_defaults: " + ", ".join(f"{k}={v}" for k, v in engine_defaults.items()))

        defaults = {"limit": 10}
        overrides = {}
        if limit != 10:
            overrides["limit"] = limit
        if filters is not None:
            overrides["filters"] = True

        result.debug.update(
            {
                "tool": "hybrid_search",
                "lanes": ["hybrid"],
                "defaults": defaults,
                "overrides": overrides,
                "gating_errors": [],
                "notes": notes,
            }
        )
        return result


