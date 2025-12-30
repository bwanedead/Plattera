from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol


class EmbeddingProvider(Protocol):
    def embed(self, texts: List[str]) -> List[List[float]]: ...


@dataclass
class NoopEmbeddingProvider:
    """
    Placeholder embedding provider. Returns empty vectors.
    """

    dim: int = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[] for _ in texts]


