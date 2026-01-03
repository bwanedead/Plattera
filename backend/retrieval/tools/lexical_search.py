from __future__ import annotations

"""
Lexical retrieval tool wrapper.

Defaults:
- mode: "both" (raw + normalized)
- view: FINALIZED unless provided in filters
- limit: 10

Debug schema keys:
tool, lanes, defaults, overrides, gating_errors, notes
"""

from dataclasses import dataclass
from typing import Optional

from corpus.types import CorpusView

from ..engine.retrieval_engine import RetrievalEngine
from ..filters.models import RetrievalFilters
from ..evidence.models import RetrievalResult


@dataclass
class LexicalSearchTool:
    engine: RetrievalEngine

    def __call__(
        self,
        query: str,
        *,
        filters: Optional[RetrievalFilters] = None,
        mode: str = "both",
        limit: int = 10,
    ) -> RetrievalResult:
        mode_key = mode.strip().lower()
        if mode_key == "raw":
            lanes = ["lexical.raw"]
        elif mode_key == "normalized":
            lanes = ["lexical.normalized"]
        elif mode_key == "both":
            lanes = ["lexical.raw", "lexical.normalized"]
        else:
            raise ValueError(f"Unknown lexical mode: {mode!r}")
        resolved_filters = _with_default_view(filters, CorpusView.FINALIZED)
        result = self.engine.search(query, filters=resolved_filters, limit=limit, lanes=lanes)

        defaults = {"mode": "both", "view": CorpusView.FINALIZED.value, "limit": 10}
        overrides = {}
        if mode_key != "both":
            overrides["mode"] = mode_key
        if filters and filters.view is not None:
            overrides["view"] = filters.view.value
        if limit != 10:
            overrides["limit"] = limit
        if filters is not None:
            overrides["filters"] = True

        result.debug.update(
            {
                "tool": "lexical_search",
                "lanes": lanes,
                "defaults": defaults,
                "overrides": overrides,
                "gating_errors": [],
                "notes": [],
            }
        )
        return result


def _with_default_view(filters: Optional[RetrievalFilters], view: CorpusView) -> RetrievalFilters:
    if not filters:
        return RetrievalFilters(view=view)
    if filters.view is not None:
        return filters
    return RetrievalFilters(
        view=view,
        dossier_id=filters.dossier_id,
        transcription_id=filters.transcription_id,
        artifact_type=filters.artifact_type,
        since_iso=filters.since_iso,
        until_iso=filters.until_iso,
        extra=dict(filters.extra or {}),
    )


