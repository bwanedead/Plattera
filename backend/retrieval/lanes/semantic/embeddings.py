from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Protocol

from .provider import EmbeddingAssetMissingError, EmbeddingModelInfo, resolve_embedding_model
from services.assets.registry import EMBEDDING_MODEL_ASSET_ID
from services.assets.service import AssetsService


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


@dataclass
class MissingEmbeddingProvider:
    asset_id: str

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise EmbeddingAssetMissingError(self.asset_id)


@dataclass
class SentenceTransformersEmbeddingProvider:
    model_info: EmbeddingModelInfo
    batch_size: int = 16
    _model: object = field(default=None, init=False, repr=False)

    def embed(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def _load_model(self) -> object:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(
                str(self.model_info.model_dir),
                local_files_only=True,
            )
        return self._model


def build_embedding_provider(
    *,
    assets_service: AssetsService | None = None,
    batch_size: int = 16,
) -> EmbeddingProvider:
    service = assets_service or AssetsService()
    try:
        model_info = resolve_embedding_model(service)
    except EmbeddingAssetMissingError:
        return MissingEmbeddingProvider(asset_id=EMBEDDING_MODEL_ASSET_ID)
    return SentenceTransformersEmbeddingProvider(model_info=model_info, batch_size=batch_size)




