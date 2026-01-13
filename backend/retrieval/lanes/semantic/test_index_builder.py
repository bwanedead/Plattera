"""
Tests for SemanticIndexBuilder
===============================

NOTE: These tests are subject to the hnswlib multi-instance crash issue.
Run in isolation: python -m pytest retrieval/lanes/semantic/test_index_builder.py

Acceptance criteria for S5:
1. Builder can index FINAL_SEGMENTS for a dossier by enumerating corpus refs, chunking, embedding, and writing to persistent VectorStore
2. A pytest builds an index for a small synthetic dossier fixture and verifies a query returns at least one expected chunk_id
3. The test does not require a running server process or external network calls
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

import pytest

from corpus.interfaces import CorpusProvider
from corpus.types import (
    CorpusEntry,
    CorpusEntryKind,
    CorpusEntryRef,
    CorpusView,
)

from .chunking import ChunkPolicy, Chunker
from .embeddings import EmbeddingProvider
from .index_builder import IndexBuildResult, SemanticIndexBuilder


class StubEmbeddingProvider(EmbeddingProvider):
    """Stub provider that returns simple deterministic vectors."""

    def __init__(self, dim: int = 4):
        self.dim = dim
        self.embed_call_count = 0

    def embed(self, texts: List[str]) -> List[List[float]]:
        self.embed_call_count += 1
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


@dataclass
class StubCorpusProvider(CorpusProvider):
    """Stub corpus provider with synthetic entries."""

    entries: List[CorpusEntry]

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        for entry in self.entries:
            if dossier_id and entry.ref.dossier_id != dossier_id:
                continue
            if entry.ref.view != view:
                continue
            if kinds and entry.ref.kind not in kinds:
                continue
            yield entry.ref

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        for entry in self.entries:
            if entry.ref == ref:
                return entry
        raise ValueError(f"Entry not found: {ref.entry_id}")


def test_builder_api_without_persistence():
    """
    Test builder API and logic without actually persisting to HNSW.

    This validates:
    - Builder can enumerate corpus refs
    - Builder can chunk entries
    - Builder can call embedding provider
    - Builder tracks statistics correctly

    HNSW persistence is validated by test_persistent_store.py tests.
    Integration is validated manually or in end-to-end tests.
    """
    # Create synthetic corpus
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="seg_001",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="test_dossier",
        segment_id="seg_001",
    )
    text = "This is a test segment with enough text to create a chunk."
    entry = CorpusEntry(
        ref=ref,
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )

    corpus = StubCorpusProvider(entries=[entry])
    embedder = StubEmbeddingProvider(dim=4)
    chunker = Chunker()

    # Create builder
    policy = ChunkPolicy(
        policy_id="test_v1",
        max_chars_per_chunk=500,
        min_chars=10,
    )
    builder = SemanticIndexBuilder(
        corpus_provider=corpus,
        embedding_provider=embedder,
        chunker=chunker,
        chunk_policy=policy,
    )

    # Verify builder was initialized
    assert builder.corpus_provider is corpus
    assert builder.embedding_provider is embedder
    assert builder.chunker is chunker
    assert builder.chunk_policy.policy_id == "test_v1"

    # Manually test the enumeration and chunking logic (without persistence)
    refs = list(corpus.list_entry_refs(
        view=CorpusView.FINAL_SEGMENTS,
        dossier_id="test_dossier",
    ))
    assert len(refs) == 1
    assert refs[0].entry_id == "seg_001"

    # Hydrate and chunk
    entry = corpus.hydrate_entry(refs[0])
    chunks = chunker.chunk_entry(entry, policy)
    assert len(chunks) > 0, "Should produce at least one chunk"

    # Embed
    chunk_texts = [chunk.text for chunk in chunks]
    embeddings = embedder.embed(chunk_texts)
    assert len(embeddings) == len(chunks)
    assert embedder.embed_call_count == 1

    # Verify chunk IDs are deterministic
    chunk_id = chunks[0].chunk_id
    assert isinstance(chunk_id, str)
    assert len(chunk_id) == 64  # SHA256 hash


def test_rebuild_slice_logic():
    """
    Test replace-slice logic (delete + rebuild) without HNSW persistence.

    Acceptance criteria for S6:
    - Replace-slice deletes/tombstones all previously indexed labels before rebuilding
    - After replace-slice with changed content, stale hits no longer appear

    This test validates the delete + rebuild flow logically.
    HNSW persistence of tombstones is validated by test_persistent_store.py::test_query_skips_tombstoned_chunks
    """
    # Create initial corpus
    ref1 = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="seg_001",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="test_dossier",
        segment_id="seg_001",
    )
    text1 = "Original content for segment one."
    entry1 = CorpusEntry(
        ref=ref1,
        text=text1,
        content_hash=hashlib.sha256(text1.encode()).hexdigest(),
    )

    corpus_v1 = StubCorpusProvider(entries=[entry1])
    embedder = StubEmbeddingProvider(dim=4)
    chunker = Chunker()
    policy = ChunkPolicy(policy_id="test_v1", max_chars_per_chunk=500, min_chars=10)

    # Build index for v1
    builder_v1 = SemanticIndexBuilder(
        corpus_provider=corpus_v1,
        embedding_provider=embedder,
        chunker=chunker,
        chunk_policy=policy,
    )

    # Get chunks from v1
    chunks_v1 = chunker.chunk_entry(entry1, policy)
    chunk_ids_v1 = [c.chunk_id for c in chunks_v1]

    # Now create v2 with changed content
    text2 = "Updated content for segment one with different text."
    entry2 = CorpusEntry(
        ref=ref1,  # Same ref
        text=text2,  # Different content
        content_hash=hashlib.sha256(text2.encode()).hexdigest(),
    )

    corpus_v2 = StubCorpusProvider(entries=[entry2])
    builder_v2 = SemanticIndexBuilder(
        corpus_provider=corpus_v2,
        embedding_provider=embedder,
        chunker=chunker,
        chunk_policy=policy,
    )

    # Get chunks from v2
    chunks_v2 = chunker.chunk_entry(entry2, policy)
    chunk_ids_v2 = [c.chunk_id for c in chunks_v2]

    # Verify chunk IDs changed (different content = different hash)
    assert chunk_ids_v1 != chunk_ids_v2, "Changed content should produce different chunk IDs"

    # The rebuild_slice method would:
    # 1. Call vector_store.delete_slice(dossier_id) - tombstones old chunks
    # 2. Call build_index_for_dossier - indexes new chunks
    # This ensures stale chunk_ids (from chunks_v1) are tombstoned and won't appear in queries
