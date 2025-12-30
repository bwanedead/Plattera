from __future__ import annotations

from dataclasses import dataclass

from retrieval.engine.retrieval_engine import RetrievalEngine
from retrieval.tools.hybrid_search import HybridSearchTool
from retrieval.tools.lexical_search import LexicalSearchTool
from retrieval.tools.semantic_search import SemanticSearchTool


@dataclass
class Toolbelt:
    """
    A single place to wire agent-facing tools/services.

    v0: retrieval only; later adds dossier services, pipeline invocations, etc.
    """

    retrieval: RetrievalEngine = RetrievalEngine()

    @property
    def lexical_search(self) -> LexicalSearchTool:
        return LexicalSearchTool(engine=self.retrieval)

    @property
    def semantic_search(self) -> SemanticSearchTool:
        return SemanticSearchTool(engine=self.retrieval)

    @property
    def hybrid_search(self) -> HybridSearchTool:
        return HybridSearchTool(engine=self.retrieval)


