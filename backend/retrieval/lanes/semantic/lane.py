from __future__ import annotations

import json
import threading
import time
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
from .embeddings import EmbeddingAssetMissingError, EmbeddingProvider, build_embedding_provider, SentenceTransformersEmbeddingProvider
from .chunking import FINAL_SEGMENTS_POLICY
from .manifest import SemanticIndexManifest, hnsw_index_path, metadata_db_path, read_manifest
from .metadata_store import VectorMetadataStore
from .worker.protocol import manifest_fingerprint
from .worker.supervisor import get_supervisor


class IndexLoadStatus(Enum):
    """Status of index load attempt."""
    SUCCESS = "success"
    NOT_INITIALIZED = "not_initialized"  # Files absent
    UNAVAILABLE = "unavailable"  # Files present but failed to load


@dataclass
class IndexLoadResult:
    """Result of attempting to load metadata store."""
    status: IndexLoadStatus
    vector_store: Optional[VectorMetadataStore] = None
    error: Optional[str] = None
    metadata_cached: bool = False


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
    _metadata_store: Optional[VectorMetadataStore] = field(default=None, init=False, repr=False)
    _embedding_provider: Optional[EmbeddingProvider] = field(default=None, init=False, repr=False)
    _embedding_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def search(self, query: str, *, filters: RetrievalFilters | None = None, limit: int = 10) -> RetrievalResult:
        total_started = time.monotonic()
        # Build embedding provider
        try:
            embed_started = time.monotonic()
            provider = self._get_or_create_embedding_provider()
            with self._embedding_lock:
                embeddings = provider.embed([query])
            embed_ms = int((time.monotonic() - embed_started) * 1000)
        except EmbeddingAssetMissingError:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["embedding_model_missing"],
                    "asset_id": EMBEDDING_MODEL_ASSET_ID,
                    "embed_ms": int((time.monotonic() - total_started) * 1000),
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
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
                    "embed_ms": int((time.monotonic() - total_started) * 1000),
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
                },
            )

        if not embeddings or not embeddings[0]:
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "gating_errors": ["embedding_empty"],
                    "embed_ms": embed_ms,
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
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
                    "embed_ms": embed_ms,
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
                },
            )

        # Try to load metadata store (no HNSW in-process)
        metadata_started = time.monotonic()
        load_result = self._get_or_load_metadata_store()
        metadata_open_ms = int((time.monotonic() - metadata_started) * 1000)

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
                    "embed_ms": embed_ms,
                    "metadata_open_ms": metadata_open_ms,
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
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
                    "embed_ms": embed_ms,
                    "metadata_open_ms": metadata_open_ms,
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
                },
            )

        metadata_store = load_result.vector_store
        assert metadata_store is not None, "SUCCESS status must have metadata_store"

        # Read manifest for provenance metadata (S8: embedding model id, chunking policy id)
        manifest_started = time.monotonic()
        manifest = read_manifest(pool_identifier=self.pool_identifier)
        manifest_ms = int((time.monotonic() - manifest_started) * 1000)
        fingerprint = manifest_fingerprint(manifest)

        supervisor = get_supervisor(self.pool_identifier)
        worker_started = time.monotonic()
        response, reason = supervisor.query(
            vector=query_vector,
            k=limit,
            embedding_dim=embedding_dim,
            manifest_fingerprint=fingerprint,
        )
        worker_knn_ms = int((time.monotonic() - worker_started) * 1000)
        if response.status != "ok":
            return RetrievalResult(
                query=query,
                cards=[],
                debug={
                    "lane": self.lane_name,
                    "reason": reason or response.reason_code or "semantic_worker_unavailable",
                    "pool_identifier": self.pool_identifier,
                    "embed_ms": embed_ms,
                    "manifest_ms": manifest_ms,
                    "metadata_open_ms": metadata_open_ms,
                    "metadata_cached": load_result.metadata_cached,
                    "worker_knn_ms": worker_knn_ms,
                    "total_lane_ms": int((time.monotonic() - total_started) * 1000),
                },
            )

        hits = response.results

        # Convert hits to EvidenceCards
        cards = []
        for label, distance in hits:
            # Lookup metadata to get entry_id and selector
            metadata = metadata_store.lookup_by_label(label)
            if metadata is None:
                continue  # Missing metadata, skip
            if metadata.is_deleted:
                continue

            # Parse selector from JSON
            try:
                selector_dict = json.loads(metadata.selector_json)
                selector = ChunkSelector(**selector_dict)
            except Exception:
                selector = None

            # Build CorpusEntryRef based on pool
            if self.pool_identifier == "EVERYTHING":
                entry_ref = CorpusEntryRef(
                    view=CorpusView.EVERYTHING,
                    entry_id=metadata.entry_id,
                    kind=CorpusEntryKind.TRANSCRIPT,
                    dossier_id=metadata.dossier_id,
                    draft_id=metadata.draft_id,
                )
            else:
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
                chunk_id=metadata.chunk_id,
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
                id=metadata.chunk_id,
                spans=[span],
                score=1.0 - distance,  # Convert distance to similarity score
                lane=self.lane_name,
                provenance={"chunk_id": metadata.chunk_id, "distance": distance},
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
                "embed_ms": embed_ms,
                "manifest_ms": manifest_ms,
                "metadata_open_ms": metadata_open_ms,
                "metadata_cached": load_result.metadata_cached,
                "worker_knn_ms": worker_knn_ms,
                "total_lane_ms": int((time.monotonic() - total_started) * 1000),
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

        # Check embedding model fingerprint (if available)
        if manifest.embedding_model_fingerprint is not None:
            # Manifest has fingerprint: use robust fingerprint comparison
            if isinstance(embedding_provider, SentenceTransformersEmbeddingProvider):
                from .embeddings import compute_model_fingerprint
                runtime_fingerprint = compute_model_fingerprint(embedding_provider.model_info)

                if manifest.embedding_model_fingerprint != runtime_fingerprint:
                    return f"embedding_model_fingerprint_mismatch: manifest={manifest.embedding_model_fingerprint}, runtime={runtime_fingerprint}"
            # If provider doesn't have model_info, can't compute fingerprint, skip check
        else:
            # Manifest has no fingerprint: fall back to model_id comparison (backward compat)
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

    def _get_or_load_metadata_store(self) -> IndexLoadResult:
        """
        Load metadata store if it exists.

        Returns IndexLoadResult with explicit status:
        - SUCCESS: Store loaded successfully
        - NOT_INITIALIZED: Index files absent (not built yet)
        - UNAVAILABLE: Index files present but failed to load (corrupt/incompatible)
        """
        if self._metadata_store is not None:
            return IndexLoadResult(
                status=IndexLoadStatus.SUCCESS,
                vector_store=self._metadata_store,
                metadata_cached=True,
            )

        hnsw_path = hnsw_index_path(pool_identifier=self.pool_identifier)
        metadata_path = metadata_db_path(pool_identifier=self.pool_identifier)

        # Check if index files exist
        if not metadata_path.exists() or not hnsw_path.exists():
            return IndexLoadResult(
                status=IndexLoadStatus.NOT_INITIALIZED,
                error=f"Index files missing: hnsw={hnsw_path.exists()}, metadata={metadata_path.exists()}",
            )

        # Try to load (files exist but may be corrupt/incompatible)
        try:
            self._metadata_store = VectorMetadataStore(metadata_path)
            return IndexLoadResult(
                status=IndexLoadStatus.SUCCESS,
                vector_store=self._metadata_store,
                metadata_cached=False,
            )
        except Exception as e:
            # Failed to load (corrupted, wrong dim, etc.)
            return IndexLoadResult(
                status=IndexLoadStatus.UNAVAILABLE,
                error=f"Failed to load index: {type(e).__name__}: {str(e)}",
            )

    def _get_or_create_embedding_provider(self) -> EmbeddingProvider:
        if self._embedding_provider is not None:
            return self._embedding_provider
        with self._embedding_lock:
            if self._embedding_provider is None:
                self._embedding_provider = build_embedding_provider(
                    assets_service=self.assets_service,
                    batch_size=self.batch_size,
                )
        return self._embedding_provider
