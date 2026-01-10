from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ...evidence.models import RetrievalResult
from ...filters.models import RetrievalFilters
from services.assets.registry import EMBEDDING_MODEL_ASSET_ID
from services.assets.service import AssetsService

from .embeddings import EmbeddingAssetMissingError, build_embedding_provider, SentenceTransformersEmbeddingProvider


class SemanticLane(Protocol):
    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult: ...


@dataclass
class NoopSemanticLane:
    lane_name: str = "semantic:noop"
    assets_service: AssetsService = field(default_factory=AssetsService)

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        status = self.assets_service.get_asset_status(EMBEDDING_MODEL_ASSET_ID)
        if status.value != "installed":
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["embedding_model_missing"],
                },
            )
        return RetrievalResult(
            query=query,
            cards=[],
            debug={
                "lane": self.lane_name,
                "note": "semantic_unimplemented",
            },
        )


@dataclass
class LocalSemanticLane:
    lane_name: str = "semantic:local"
    assets_service: AssetsService = field(default_factory=AssetsService)
    batch_size: int = 16

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        try:
            provider = build_embedding_provider(
                assets_service=self.assets_service,
                batch_size=self.batch_size,
            )
            embeddings = provider.embed([query])
        except EmbeddingAssetMissingError:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["embedding_model_missing"],
                    "asset_id": EMBEDDING_MODEL_ASSET_ID,
                },
            )
        except Exception as exc:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["embedding_model_unavailable"],
                    "asset_id": EMBEDDING_MODEL_ASSET_ID,
                    "error": type(exc).__name__,
                },
            )

        dim = len(embeddings[0]) if embeddings and embeddings[0] else 0
        model_dir = None
        requested_revision = None
        resolved_revision = None
        if isinstance(provider, SentenceTransformersEmbeddingProvider):
            model_dir = str(provider.model_info.model_dir)
            manifest = provider.model_info.manifest or {}
            requested_revision = manifest.get("requested_revision") or manifest.get("revision")
            resolved_revision = manifest.get("resolved_revision") or manifest.get("revision")

        return RetrievalResult(
            query=query,
            cards=[],
            debug={
                "lane": self.lane_name,
                "asset_id": EMBEDDING_MODEL_ASSET_ID,
                "model_dir": model_dir,
                "requested_revision": requested_revision,
                "resolved_revision": resolved_revision,
                "embedding_dim": dim,
                "note": "semantic_embeddings_loaded",
            },
        )




