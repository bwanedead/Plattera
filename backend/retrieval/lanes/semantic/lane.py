from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

from corpus.types import CorpusChunkRef, CorpusEntryRef, CorpusEntryKind, CorpusView
from ...evidence.models import EvidenceCard, EvidenceSpan, RetrievalResult
from ...filters.models import RetrievalFilters
from services.assets.registry import EMBEDDING_MODEL_ASSET_ID
from services.assets.service import AssetsService

from .chunking import ChunkSelector
from .embeddings import EmbeddingAssetMissingError, build_embedding_provider, SentenceTransformersEmbeddingProvider
from .chunking import FINAL_SEGMENTS_POLICY
from .manifest import SemanticIndexManifest, hnsw_index_path, metadata_db_path, read_manifest
from .persistent_store import PersistentVectorStore, load_persistent_store


class IndexLoadStatus(Enum):
    """Status of index load attempt."""
    SUCCESS = "success"
    NOT_INITIALIZED = "not_initialized"  # Files absent
    UNAVAILABLE = "unavailable"  # Files present but failed to load


@dataclass
class IndexLoadResult:
    """Result of attempting to load vector store."""
    status: IndexLoadStatus
    vector_store: Optional[PersistentVectorStore] = None
    error: Optional[str] = None


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
    pool_identifier: str = "FINAL_SEGMENTS"
    _vector_store: Optional[PersistentVectorStore] = field(default=None, init=False, repr=False)

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        # Build embedding provider
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

        if not embeddings or not embeddings[0]:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["embedding_empty"],
                },
            )

        query_vector = embeddings[0]
        embedding_dim = len(query_vector)

        # Check for manifest mismatch (stale index)
        stale_reason = self._check_manifest_mismatch(embedding_dim, provider)
        if stale_reason is not None:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "reason": "index_stale_needs_reindex",
                    "stale_reason": stale_reason,
                    "pool_identifier": self.pool_identifier,
                },
            )

        # Try to load vector store
        load_result = self._get_or_load_vector_store(embedding_dim)

        if load_result.status == IndexLoadStatus.NOT_INITIALIZED:
            # Index files absent (not built yet)
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "reason": "index_not_initialized",
                    "pool_identifier": self.pool_identifier,
                    "error": load_result.error,
                },
            )

        if load_result.status == IndexLoadStatus.UNAVAILABLE:
            # Index files present but failed to load
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "reason": "index_unavailable",
                    "pool_identifier": self.pool_identifier,
                    "error": load_result.error,
                },
            )

        vector_store = load_result.vector_store
        assert vector_store is not None, "SUCCESS status must have vector_store"

        # Read manifest for provenance metadata (S8: embedding model id, chunking policy id)
        manifest = read_manifest(pool_identifier=self.pool_identifier)

        # Query vector store
        try:
            hits = vector_store.query(vector=query_vector, k=limit)
        except Exception as exc:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["vector_query_failed"],
                    "error": type(exc).__name__,
                },
            )

        # Convert hits to EvidenceCards
        cards = []
        for chunk_id, distance in hits:
            # Lookup metadata to get entry_id and selector
            metadata = vector_store.metadata_store.lookup_by_chunk_id(chunk_id)
            if metadata is None:
                continue  # Missing metadata, skip

            # Parse selector from JSON
            try:
                selector_dict = json.loads(metadata.selector_json)
                selector = ChunkSelector(**selector_dict)
            except Exception:
                selector = None

            # Build CorpusEntryRef with full fidelity for FINAL_SEGMENTS
            entry_ref = CorpusEntryRef(
                view=CorpusView.FINAL_SEGMENTS,
                entry_id=metadata.entry_id,
                kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
                dossier_id=metadata.dossier_id,
                segment_id=metadata.segment_id,
                draft_id=metadata.draft_id,
            )

            # Build CorpusChunkRef
            chunk_ref = CorpusChunkRef(
                entry=entry_ref,
                chunk_id=chunk_id,
                metadata=selector_dict if selector else {},
            )

            # Build provenance metadata for this match (S8)
            span_metadata = {
                "pool_identifier": self.pool_identifier,
                "distance": distance,
                "similarity_score": 1.0 - distance,
            }

            # Add manifest provenance if available
            if manifest is not None:
                span_metadata["embedding_model_id"] = manifest.embedding_model_id
                span_metadata["chunking_policy_id"] = manifest.chunking_policy_id
                span_metadata["embedding_dim"] = manifest.embedding_dim

            # Create EvidenceSpan with preview and provenance metadata
            span = EvidenceSpan(
                entry=entry_ref,
                text="",  # Text not stored in index; would need hydration
                chunk=chunk_ref,
                preview=metadata.preview,
                metadata=span_metadata,
            )

            # Create EvidenceCard
            card = EvidenceCard(
                id=chunk_id,
                spans=[span],
                score=1.0 - distance,  # Convert distance to similarity score
                lane=self.lane_name,
                provenance={"chunk_id": chunk_id, "distance": distance},
            )
            cards.append(card)

        return RetrievalResult(
            query=query,
            cards=cards,
            debug={
                "lane": self.lane_name,
                "embedding_dim": embedding_dim,
                "hits_count": len(hits),
                "cards_count": len(cards),
            },
        )

    def _check_manifest_mismatch(
        self,
        runtime_embedding_dim: int,
        embedding_provider,
    ) -> Optional[str]:
        """
        Check if runtime config mismatches persisted manifest.

        Returns:
            None if no mismatch or manifest missing
            String reason if mismatch detected
        """
        # Try to read manifest
        try:
            manifest = read_manifest(pool_identifier=self.pool_identifier)
        except Exception:
            # Manifest missing or corrupt - not a mismatch, just uninited
            return None

        if manifest is None:
            # No manifest = not initialized yet
            return None

        # Check embedding dimension
        if manifest.embedding_dim != runtime_embedding_dim:
            return f"embedding_dim_mismatch: manifest={manifest.embedding_dim}, runtime={runtime_embedding_dim}"

        # Check embedding model ID
        runtime_model_id = "unknown"
        if isinstance(embedding_provider, SentenceTransformersEmbeddingProvider):
            model_info = embedding_provider.model_info
            manifest_data = model_info.manifest or {}
            runtime_model_id = manifest_data.get("resolved_revision") or manifest_data.get("revision") or "unknown"

        if manifest.embedding_model_id != runtime_model_id:
            return f"embedding_model_mismatch: manifest={manifest.embedding_model_id}, runtime={runtime_model_id}"

        # Check chunking policy
        runtime_policy_id = FINAL_SEGMENTS_POLICY.policy_id
        if manifest.chunking_policy_id != runtime_policy_id:
            return f"chunking_policy_mismatch: manifest={manifest.chunking_policy_id}, runtime={runtime_policy_id}"

        # No mismatch
        return None

    def _get_or_load_vector_store(self, embedding_dim: int) -> IndexLoadResult:
        """
        Load vector store if it exists.

        Returns IndexLoadResult with explicit status:
        - SUCCESS: Store loaded successfully
        - NOT_INITIALIZED: Index files absent (not built yet)
        - UNAVAILABLE: Index files present but failed to load (corrupt/incompatible)
        """
        if self._vector_store is not None:
            return IndexLoadResult(
                status=IndexLoadStatus.SUCCESS,
                vector_store=self._vector_store,
            )

        # Resolve paths
        hnsw_path = hnsw_index_path(pool_identifier=self.pool_identifier)
        metadata_path = metadata_db_path(pool_identifier=self.pool_identifier)

        # Check if index files exist
        if not hnsw_path.exists() or not metadata_path.exists():
            return IndexLoadResult(
                status=IndexLoadStatus.NOT_INITIALIZED,
                error=f"Index files missing: hnsw={hnsw_path.exists()}, metadata={metadata_path.exists()}",
            )

        # Try to load (files exist but may be corrupt/incompatible)
        try:
            self._vector_store = load_persistent_store(
                pool_identifier=self.pool_identifier,
                embedding_dim=embedding_dim,
                hnsw_path=hnsw_path,
                metadata_db_path=metadata_path,
            )
            return IndexLoadResult(
                status=IndexLoadStatus.SUCCESS,
                vector_store=self._vector_store,
            )
        except Exception as e:
            # Failed to load (corrupted, wrong dim, etc.)
            return IndexLoadResult(
                status=IndexLoadStatus.UNAVAILABLE,
                error=f"Failed to load index: {type(e).__name__}: {str(e)}",
            )




