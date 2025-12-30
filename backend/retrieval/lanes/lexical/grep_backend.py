from __future__ import annotations

from dataclasses import dataclass

from ...evidence.models import RetrievalResult
from ...filters.models import RetrievalFilters


@dataclass
class GrepBackendLexicalLane:
    """
    v0 lexical lane placeholder.

    Intention: hydrate corpus docs and do basic substring/regex scanning.
    We keep it unimplemented for now to avoid committing to chunking/index layout.
    """

    lane_name: str = "lexical:grep_backend"

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        return RetrievalResult(
            query=query,
            cards=[],
            debug={"lane": self.lane_name, "note": "unimplemented_v0"},
        )


