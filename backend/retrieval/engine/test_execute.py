from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView

from ..lanes.semantic.chunking import ChunkPolicy, Chunker
from ..lanes.semantic.embeddings import EmbeddingProvider
from ..lanes.semantic.index_builder import SemanticIndexBuilder
from ..lanes.semantic.metadata_store import ChunkMetadata, VectorMetadataStore
from .diagnose import RuntimeIndexIdentity, SliceDiagnoser, SliceStatus
from .execute import SliceExecutor


@dataclass
class StubCorpusProvider(CorpusProvider):
    entries: List[CorpusEntry]

    def list_entry_refs(
        self,
        view: CorpusView,
        *,
        dossier_id: Optional[str] = None,
        kinds: Optional[Set[CorpusEntryKind]] = None,
    ) -> Iterable[CorpusEntryRef]:
        for entry in self.entries:
            if entry.ref.view != view:
                continue
            if dossier_id and entry.ref.dossier_id != dossier_id:
                continue
            if kinds and entry.ref.kind not in kinds:
                continue
            yield entry.ref

    def hydrate_entry(self, ref: CorpusEntryRef) -> CorpusEntry:
        for entry in self.entries:
            if entry.ref == ref:
                return entry
        raise ValueError(f"Entry not found: {ref.entry_id}")


class StubEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dim: int = 4):
        self.dim = dim

    def embed(self, texts: List[str]) -> List[List[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


class StubVectorStore:
    def __init__(self, pool_identifier: str, metadata_path: Path):
        self.pool_identifier = pool_identifier
        self.metadata_store = VectorMetadataStore(metadata_path)

    def upsert(
        self,
        chunk_id: str,
        vector: List[float],
        dossier_id: Optional[str],
        entry_id: str,
        selector_json: str,
        preview: Optional[str] = None,
        segment_id: Optional[str] = None,
        draft_id: Optional[str] = None,
    ) -> None:
        label = self.metadata_store.get_next_label()
        metadata = ChunkMetadata(
            chunk_id=chunk_id,
            label=label,
            dossier_id=dossier_id,
            pool_identifier=self.pool_identifier,
            entry_id=entry_id,
            selector_json=selector_json,
            preview=preview,
            segment_id=segment_id,
            draft_id=draft_id,
            is_deleted=False,
        )
        self.metadata_store.upsert_chunk(metadata)

    def delete_entry_slice(self, dossier_id: str, entry_id: str) -> int:
        labels = self.metadata_store.list_labels_for_entry(
            pool_identifier=self.pool_identifier,
            dossier_id=dossier_id,
            entry_id=entry_id,
        )
        self.metadata_store.mark_deleted(labels)
        return len(labels)


def _make_entry(
    dossier_id: str,
    entry_id: str,
    text: str,
    *,
    view: CorpusView = CorpusView.FINAL_SEGMENTS,
    kind: CorpusEntryKind = CorpusEntryKind.SEGMENT_FINAL_TEXT,
    draft_id: Optional[str] = None,
) -> CorpusEntry:
    ref = CorpusEntryRef(
        view=view,
        entry_id=entry_id,
        kind=kind,
        dossier_id=dossier_id,
        draft_id=draft_id,
    )
    return CorpusEntry(
        ref=ref,
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )


def test_execute_rebuilds_only_stale_slice() -> None:
    policy = ChunkPolicy(policy_id="exec_policy_v1", max_chars_per_chunk=500, min_chars=10)
    chunker = Chunker()
    embedder = StubEmbeddingProvider()

    entry_a_v1 = _make_entry("D1", "segment_final:D1:seg_001:T1", "Alpha v1 text")
    entry_b_v1 = _make_entry("D1", "segment_final:D1:seg_002:T1", "Beta v1 text")

    corpus_v1 = StubCorpusProvider(entries=[entry_a_v1, entry_b_v1])

    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_path = Path(tmpdir) / "metadata.db"
        vector_store = StubVectorStore(pool_identifier="FINAL_SEGMENTS", metadata_path=metadata_path)

        builder_v1 = SemanticIndexBuilder(
            corpus_provider=corpus_v1,
            embedding_provider=embedder,
            chunker=chunker,
            chunk_policy=policy,
        )

        build_result = builder_v1.build_index_for_dossier(
            vector_store=vector_store,
            dossier_id="D1",
            view=CorpusView.FINAL_SEGMENTS,
            embedding_model_fingerprint="model_v1",
        )
        assert build_result.errors == []

        entry_a_chunks_v1 = chunker.chunk_entry(entry_a_v1, policy)
        entry_b_chunks_v1 = chunker.chunk_entry(entry_b_v1, policy)

        entry_a_v2 = _make_entry("D1", "segment_final:D1:seg_001:T1", "Alpha v2 text updated")
        corpus_v2 = StubCorpusProvider(entries=[entry_a_v2, entry_b_v1])

        runtime_identity = RuntimeIndexIdentity(
            embedding_model_fingerprint="model_v1",
            chunking_policy_id=policy.policy_id,
        )

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus_v2,
            metadata_store=vector_store.metadata_store,
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=runtime_identity,
        )

        statuses = {d.entry_id: d.status for d in diagnoser.diagnose(dossier_id="D1")}
        assert statuses[entry_a_v1.ref.entry_id] == SliceStatus.STALE_CONTENT
        assert statuses[entry_b_v1.ref.entry_id] == SliceStatus.HEALTHY

        executor = SliceExecutor(
            corpus_provider=corpus_v2,
            vector_store=vector_store,
            builder=SemanticIndexBuilder(
                corpus_provider=corpus_v2,
                embedding_provider=embedder,
                chunker=chunker,
                chunk_policy=policy,
            ),
            runtime_identity=runtime_identity,
        )

        exec_result = executor.execute_entry(
            dossier_id="D1",
            entry_id=entry_a_v1.ref.entry_id,
        )
        assert exec_result.status == SliceStatus.HEALTHY
        assert exec_result.deleted_count == len(entry_a_chunks_v1)
        assert exec_result.did_write_state is True  # H2: state written on success

        for chunk in entry_a_chunks_v1:
            meta = vector_store.metadata_store.lookup_by_chunk_id(chunk.chunk_id)
            assert meta is not None
            assert meta.is_deleted is True

        for chunk in entry_b_chunks_v1:
            meta = vector_store.metadata_store.lookup_by_chunk_id(chunk.chunk_id)
            assert meta is not None
            assert meta.is_deleted is False

        entry_a_chunks_v2 = chunker.chunk_entry(entry_a_v2, policy)
        for chunk in entry_a_chunks_v2:
            meta = vector_store.metadata_store.lookup_by_chunk_id(chunk.chunk_id)
            assert meta is not None
            assert meta.is_deleted is False

        post_statuses = {
            d.entry_id: d.status for d in diagnoser.diagnose(dossier_id="D1")
        }
        assert post_statuses[entry_a_v1.ref.entry_id] == SliceStatus.HEALTHY
        assert post_statuses[entry_b_v1.ref.entry_id] == SliceStatus.HEALTHY


def test_execute_no_state_write_on_vector_failure() -> None:
    """
    H2 Test: Verify that indexed_entry_state is NOT written if vector upserts fail.
    """
    policy = ChunkPolicy(policy_id="fail_policy_v1", max_chars_per_chunk=500, min_chars=10)
    chunker = Chunker()
    embedder = StubEmbeddingProvider()

    entry = _make_entry("D1", "segment_final:D1:seg_001:T1", "Test text")
    corpus = StubCorpusProvider(entries=[entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_path = Path(tmpdir) / "metadata.db"

        # Create a failing vector store that throws on upsert
        class FailingVectorStore(StubVectorStore):
            def upsert(self, *args, **kwargs):
                raise RuntimeError("Simulated vector upsert failure")

        vector_store = FailingVectorStore(pool_identifier="FINAL_SEGMENTS", metadata_path=metadata_path)

        runtime_identity = RuntimeIndexIdentity(
            embedding_model_fingerprint="model_v1",
            chunking_policy_id=policy.policy_id,
        )

        builder = SemanticIndexBuilder(
            corpus_provider=corpus,
            embedding_provider=embedder,
            chunker=chunker,
            chunk_policy=policy,
        )

        executor = SliceExecutor(
            corpus_provider=corpus,
            vector_store=vector_store,
            builder=builder,
            runtime_identity=runtime_identity,
        )

        # Execute should fail due to upsert failure
        exec_result = executor.execute_entry(
            dossier_id="D1",
            entry_id=entry.ref.entry_id,
        )

        # H2: Verify failure status and no state write
        assert exec_result.status != SliceStatus.HEALTHY
        assert exec_result.did_write_state is False
        assert exec_result.chunks_added == 0
        assert "Upsert failed" in exec_result.reason or ""

        # H2: Verify indexed_entry_state was NOT written
        state = vector_store.metadata_store.get_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id=entry.ref.entry_id,
        )
        assert state is None  # No state written due to failure


def test_execute_rebuilds_only_stale_everything_slice() -> None:
    policy = ChunkPolicy(policy_id="exec_policy_everything_v1", max_chars_per_chunk=500, min_chars=10)
    chunker = Chunker()
    embedder = StubEmbeddingProvider()

    entry_a_id = "draft:head:D1:T1"
    entry_b_id = "draft:head:D1:T2"

    entry_a_v1 = _make_entry(
        "D1",
        entry_a_id,
        "Alpha transcript v1",
        view=CorpusView.EVERYTHING,
        kind=CorpusEntryKind.TRANSCRIPT,
        draft_id=entry_a_id,
    )
    entry_b_v1 = _make_entry(
        "D1",
        entry_b_id,
        "Beta transcript v1",
        view=CorpusView.EVERYTHING,
        kind=CorpusEntryKind.TRANSCRIPT,
        draft_id=entry_b_id,
    )

    corpus_v1 = StubCorpusProvider(entries=[entry_a_v1, entry_b_v1])

    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_path = Path(tmpdir) / "metadata.db"
        vector_store = StubVectorStore(pool_identifier="EVERYTHING", metadata_path=metadata_path)

        builder_v1 = SemanticIndexBuilder(
            corpus_provider=corpus_v1,
            embedding_provider=embedder,
            chunker=chunker,
            chunk_policy=policy,
        )

        build_result = builder_v1.build_index_for_dossier(
            vector_store=vector_store,
            dossier_id="D1",
            view=CorpusView.EVERYTHING,
            embedding_model_fingerprint="model_v1",
        )
        assert build_result.errors == []

        entry_a_chunks_v1 = chunker.chunk_entry(entry_a_v1, policy)
        entry_b_chunks_v1 = chunker.chunk_entry(entry_b_v1, policy)

        entry_a_v2 = _make_entry(
            "D1",
            entry_a_id,
            "Alpha transcript v2 updated",
            view=CorpusView.EVERYTHING,
            kind=CorpusEntryKind.TRANSCRIPT,
            draft_id=entry_a_id,
        )
        corpus_v2 = StubCorpusProvider(entries=[entry_a_v2, entry_b_v1])

        runtime_identity = RuntimeIndexIdentity(
            embedding_model_fingerprint="model_v1",
            chunking_policy_id=policy.policy_id,
        )

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus_v2,
            metadata_store=vector_store.metadata_store,
            pool_identifier="EVERYTHING",
            runtime_identity=runtime_identity,
        )

        statuses = {d.entry_id: d.status for d in diagnoser.diagnose(dossier_id="D1")}
        assert statuses[entry_a_id] == SliceStatus.STALE_CONTENT
        assert statuses[entry_b_id] == SliceStatus.HEALTHY

        executor = SliceExecutor(
            corpus_provider=corpus_v2,
            vector_store=vector_store,
            builder=SemanticIndexBuilder(
                corpus_provider=corpus_v2,
                embedding_provider=embedder,
                chunker=chunker,
                chunk_policy=policy,
            ),
            runtime_identity=runtime_identity,
        )

        exec_result = executor.execute_entry(dossier_id="D1", entry_id=entry_a_id)
        assert exec_result.status == SliceStatus.HEALTHY
        assert exec_result.deleted_count == len(entry_a_chunks_v1)

        for chunk in entry_a_chunks_v1:
            meta = vector_store.metadata_store.lookup_by_chunk_id(chunk.chunk_id)
            assert meta is not None
            assert meta.is_deleted is True

        for chunk in entry_b_chunks_v1:
            meta = vector_store.metadata_store.lookup_by_chunk_id(chunk.chunk_id)
            assert meta is not None
            assert meta.is_deleted is False

        entry_a_chunks_v2 = chunker.chunk_entry(entry_a_v2, policy)
        for chunk in entry_a_chunks_v2:
            meta = vector_store.metadata_store.lookup_by_chunk_id(chunk.chunk_id)
            assert meta is not None
            assert meta.is_deleted is False

        post_statuses = {d.entry_id: d.status for d in diagnoser.diagnose(dossier_id="D1")}
        assert post_statuses[entry_a_id] == SliceStatus.HEALTHY
        assert post_statuses[entry_b_id] == SliceStatus.HEALTHY
