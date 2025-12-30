from __future__ import annotations

from dataclasses import dataclass
from typing import List

from ...evidence.models import EvidenceCard


@dataclass
class CrossEncoderReranker:
    """
    Placeholder for a cross-encoder reranker.
    """

    model_name: str = "unset"

    def rerank(self, query: str, cards: List[EvidenceCard]) -> List[EvidenceCard]:
        # v0: no-op
        return cards


