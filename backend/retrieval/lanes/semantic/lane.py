from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from ...evidence.models import RetrievalResult
from ...filters.models import RetrievalFilters


class SemanticLane(Protocol):
    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult: ...


@dataclass
class NoopSemanticLane:
    lane_name: str = "semantic:noop"

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        return RetrievalResult(query=query, cards=[], debug={"lane": self.lane_name})


