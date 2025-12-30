from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Tuple


class VectorStore(Protocol):
    def upsert(self, ids: List[str], vectors: List[List[float]], metadatas: Optional[List[Dict[str, Any]]] = None) -> None: ...
    def query(self, vector: List[float], *, top_k: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[Tuple[str, float]]: ...


@dataclass
class NoopVectorStore:
    """
    Placeholder vector store.
    """

    def upsert(self, ids: List[str], vectors: List[List[float]], metadatas: Optional[List[Dict[str, Any]]] = None) -> None:
        return None

    def query(self, vector: List[float], *, top_k: int = 10, filters: Optional[Dict[str, Any]] = None) -> List[Tuple[str, float]]:
        return []


