from __future__ import annotations

"""
Semantic retrieval tool wrapper (noop until semantic lane implemented).

Defaults:
- lane: semantic
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
class SemanticSearchTool:
    engine: RetrievalEngine

    def __call__(self, query: str, *, filters: Optional[RetrievalFilters] = None, limit: int = 10) -> RetrievalResult:
        result = self.engine.search(query, filters=filters, limit=limit, lanes=["semantic"])
        debug = result.debug or {}
        gating_errors = list(debug.get("gating_errors", []) or [])
        notes = list(debug.get("notes", []) or [])
        result.debug.update(
            {
                "tool": "semantic_search",
                "lanes": ["semantic"],
                "defaults": {"limit": 10},
                "overrides": {"limit": limit} if limit != 10 else {},
                "gating_errors": gating_errors,
                "notes": notes,
            }
        )
        return result




