from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol

from ...evidence.models import EvidenceCard


class RerankLane(Protocol):
    def rerank(self, query: str, cards: List[EvidenceCard]) -> List[EvidenceCard]: ...


@dataclass
class NoopRerankLane:
    lane_name: str = "rerank:noop"

    def rerank(self, query: str, cards: List[EvidenceCard]) -> List[EvidenceCard]:
        return cards


