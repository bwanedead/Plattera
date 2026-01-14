"""
Semantic Index Builder for FINAL_SEGMENTS
==========================================

Builds semantic indexes for corpus views by:
1. Enumerating corpus refs from the view
2. Hydrating entries
3. Chunking entries
4. Embedding chunks
5. Upserting to persistent vector store

Design principles:
- Append-only indexing for one dossier at a time
- Deterministic chunking and IDs
- Injectable dependencies for testability
- Safe failure modes (no crashes on missing data)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryRef, CorpusView

from .chunking import FINAL_SEGMENTS_POLICY, ChunkPolicy, Chunker, CorpusChunk
from .embeddings import EmbeddingProvider
from .manifest import MANIFEST_SCHEMA_VERSION, SemanticIndexManifest, write_manifest
from .persistent_store import PersistentVectorStore


@dataclass
class IndexBuildResult:
    """Result of an index build operation."""

    chunks_added: int
    chunks_skipped: int
    entries_processed: int
    errors: List[str]


class SemanticIndexBuilder:
    """
    Builder for semantic indexes over corpus views.

    Handles FINAL_SEGMENTS view with deterministic chunking and embedding.
    """

    def __init__(
        self,
        corpus_provider: CorpusProvider,
        embedding_provider: EmbeddingProvider,
        chunker: Optional[Chunker] = None,
        chunk_policy: Optional[ChunkPolicy] = None,
    ):
        """
        Initialize the index builder.

        Args:
            corpus_provider: Source of corpus entries
            embedding_provider: Provider for generating embeddings
            chunker: Chunker for splitting entries (default: Chunker())
            chunk_policy: Chunking policy (default: FINAL_SEGMENTS_POLICY)
        """
        self.corpus_provider = corpus_provider
        self.embedding_provider = embedding_provider
        self.chunker = chunker or Chunker()
        self.chunk_policy = chunk_policy or FINAL_SEGMENTS_POLICY

    def build_index_for_dossier(
        self,
        vector_store: PersistentVectorStore,
        dossier_id: str,
        view: CorpusView = CorpusView.FINAL_SEGMENTS,
        pool_identifier: Optional[str] = None,
        embedding_dim: Optional[int] = None,
        embedding_model_id: Optional[str] = None,
        embedding_model_fingerprint: Optional[str] = None,
    ) -> IndexBuildResult:
        """
        Build index for all entries in a single dossier.

        This is an append-only operation; existing chunks are preserved.
        On successful build, writes/updates manifest.json for the pool.

        Args:
            vector_store: Target persistent vector store
            dossier_id: Dossier to index
            view: Corpus view to enumerate (default: FINAL_SEGMENTS)
            pool_identifier: Pool identifier for manifest (required for manifest write)
            embedding_dim: Embedding dimensionality (required for manifest write)
            embedding_model_id: Model identifier (required for manifest write)
            embedding_model_fingerprint: Model fingerprint (optional for manifest write)

        Returns:
            IndexBuildResult with statistics
        """
        result = IndexBuildResult(
            chunks_added=0,
            chunks_skipped=0,
            entries_processed=0,
            errors=[],
        )

        # Enumerate corpus refs for this dossier
        try:
            refs = list(
                self.corpus_provider.list_entry_refs(
                    view=view,
                    dossier_id=dossier_id,
                )
            )
        except Exception as e:
            result.errors.append(f"Failed to list entry refs: {e}")
            return result

        if not refs:
            result.errors.append(f"No entries found for dossier {dossier_id} in view {view}")
            return result

        # Process each entry
        for ref in refs:
            try:
                # Hydrate entry
                entry = self.corpus_provider.hydrate_entry(ref)
                result.entries_processed += 1

                # Chunk entry
                chunks = self.chunker.chunk_entry(entry, self.chunk_policy)

                if not chunks:
                    continue

                # Embed chunks in batch
                chunk_texts = [chunk.text for chunk in chunks]
                try:
                    embeddings = self.embedding_provider.embed(chunk_texts)
                except Exception as e:
                    result.errors.append(
                        f"Embedding failed for entry {ref.entry_id}: {e}"
                    )
                    continue

                # Upsert to vector store
                for chunk, embedding in zip(chunks, embeddings):
                    try:
                        # Generate preview: use snippet_hint if available, else first 200 chars of text
                        preview = chunk.snippet_hint
                        if preview is None and chunk.text:
                            preview = chunk.text[:200].strip()

                        vector_store.upsert(
                            chunk_id=chunk.chunk_id,
                            vector=embedding,
                            dossier_id=dossier_id,
                            entry_id=ref.entry_id,
                            selector_json=json.dumps(chunk.selector.to_dict()),
                            preview=preview,
                            segment_id=ref.segment_id,
                            draft_id=ref.draft_id,
                        )
                        result.chunks_added += 1
                    except Exception as e:
                        result.errors.append(
                            f"Upsert failed for chunk {chunk.chunk_id}: {e}"
                        )
                        result.chunks_skipped += 1

            except Exception as e:
                result.errors.append(f"Failed to process entry {ref.entry_id}: {e}")
                continue

        # Write manifest on successful build (if parameters provided)
        if pool_identifier and embedding_dim and embedding_model_id and result.chunks_added > 0 and not result.errors:
            try:
                from datetime import datetime
                now = datetime.utcnow().isoformat() + "Z"
                manifest = SemanticIndexManifest(
                    schema_version=MANIFEST_SCHEMA_VERSION,
                    pool_identifier=pool_identifier,
                    embedding_dim=embedding_dim,
                    embedding_model_id=embedding_model_id,
                    embedding_model_fingerprint=embedding_model_fingerprint,
                    chunking_policy_id=self.chunk_policy.policy_id,
                    created_at=now,
                    updated_at=now,
                )
                write_manifest(pool_identifier, manifest)
            except Exception as e:
                result.errors.append(f"Failed to write manifest: {e}")

        return result

    def rebuild_slice(
        self,
        vector_store: PersistentVectorStore,
        dossier_id: str,
        view: CorpusView = CorpusView.FINAL_SEGMENTS,
    ) -> IndexBuildResult:
        """
        Rebuild index slice for a dossier (delete + rebuild).

        This operation:
        1. Deletes all existing chunks for the dossier/view
        2. Rebuilds the index from current corpus state

        Args:
            vector_store: Target persistent vector store
            dossier_id: Dossier to rebuild
            view: Corpus view to enumerate

        Returns:
            IndexBuildResult with statistics
        """
        # Delete existing slice
        deleted_count = vector_store.delete_slice(dossier_id)

        # Rebuild from corpus
        result = self.build_index_for_dossier(
            vector_store=vector_store,
            dossier_id=dossier_id,
            view=view,
        )

        # Note: We could add deleted_count to result metadata if needed
        return result
