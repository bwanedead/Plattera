from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView

from ..lanes.semantic.metadata_store import VectorMetadataStore
from .diagnose import RuntimeIndexIdentity, SliceDiagnoser, SliceStatus
from .reason_codes import DiagnosticReasonCode


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


def test_diagnose_missing_stale_healthy() -> None:
    entry = _make_entry("D1", "segment_final:D1:seg_001:T1", "Original text")
    corpus = StubCorpusProvider(entries=[entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=RuntimeIndexIdentity(
                embedding_model_fingerprint="model_v1",
                chunking_policy_id="policy_v1",
            ),
        )

        # Missing indexed state
        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.MISSING
        assert results[0].reason == DiagnosticReasonCode.MISSING_INDEX_STATE.value

        # Stale content signature
        store.upsert_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id=entry.ref.entry_id,
            indexed_signature="stale_signature",
            embedding_model_fingerprint="model_v1",
            chunking_policy_id="policy_v1",
        )

        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.STALE_CONTENT
        assert results[0].reason == DiagnosticReasonCode.STALE_SIGNATURE_MISMATCH.value

        # Healthy state
        store.upsert_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id=entry.ref.entry_id,
            indexed_signature=entry.content_hash or "",
            embedding_model_fingerprint="model_v1",
            chunking_policy_id="policy_v1",
        )

        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.HEALTHY
        assert results[0].reason is None


def test_diagnose_unavailable_slice() -> None:
    """Test unavailable slice due to hydration failure."""
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="segment_final:D1:seg_missing:T1",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="D1",
    )
    entry = CorpusEntry(
        ref=ref,
        text="",
        content_hash=None,
        provenance={"error": "draft_not_found"},
    )
    corpus = StubCorpusProvider(entries=[entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=RuntimeIndexIdentity(
                embedding_model_fingerprint="model_v1",
                chunking_policy_id="policy_v1",
            ),
        )

        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.UNAVAILABLE
        assert results[0].reason == DiagnosticReasonCode.UNAVAILABLE_HYDRATION_FAILED.value


def test_diagnose_unavailable_missing_content_hash() -> None:
    """Test unavailable slice due to missing content hash."""
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id="segment_final:D1:seg_empty:T1",
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id="D1",
    )
    entry = CorpusEntry(
        ref=ref,
        text="",  # Empty text
        content_hash=None,
    )
    corpus = StubCorpusProvider(entries=[entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=RuntimeIndexIdentity(
                embedding_model_fingerprint="model_v1",
                chunking_policy_id="policy_v1",
            ),
        )

        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.UNAVAILABLE
        assert results[0].reason == DiagnosticReasonCode.UNAVAILABLE_MISSING_CONTENT_HASH.value


def test_diagnose_unavailable_runtime_identity_missing() -> None:
    """
    Test that diagnose returns UNAVAILABLE when runtime_identity is None.

    H4 requirement: Never mark healthy when runtime identity is missing.
    """
    entry = _make_entry("D1", "segment_final:D1:seg_001:T1", "Original text")
    corpus = StubCorpusProvider(entries=[entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # Create indexed state that would be healthy IF runtime identity was available
        store.upsert_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id=entry.ref.entry_id,
            indexed_signature=entry.content_hash or "",
            embedding_model_fingerprint="model_v1",
            chunking_policy_id="policy_v1",
        )

        # Diagnose WITHOUT runtime_identity
        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=None,  # Missing runtime identity
        )

        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.UNAVAILABLE
        assert results[0].reason == DiagnosticReasonCode.UNAVAILABLE_RUNTIME_IDENTITY_MISSING.value


def test_diagnose_stale_identity_mismatch() -> None:
    """Test stale identity due to model or policy mismatch."""
    entry = _make_entry("D1", "segment_final:D1:seg_001:T1", "Original text")
    corpus = StubCorpusProvider(entries=[entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        # Create indexed state with old model fingerprint
        store.upsert_indexed_entry_state(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id=entry.ref.entry_id,
            indexed_signature=entry.content_hash or "",
            embedding_model_fingerprint="model_v0_OLD",  # Old model
            chunking_policy_id="policy_v1",
        )

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=RuntimeIndexIdentity(
                embedding_model_fingerprint="model_v1_NEW",  # New model
                chunking_policy_id="policy_v1",
            ),
        )

        results = diagnoser.diagnose()
        assert results[0].status == SliceStatus.STALE_IDENTITY
        assert results[0].reason == DiagnosticReasonCode.STALE_IDENTITY_MISMATCH.value


def test_diagnose_respects_everything_view_mapping() -> None:
    final_entry = _make_entry("D1", "segment_final:D1:seg_001:T1", "Final text")
    draft_id = "draft:head:D1:T1"
    everything_entry = _make_entry(
        "D1",
        draft_id,
        "Everything text",
        view=CorpusView.EVERYTHING,
        kind=CorpusEntryKind.TRANSCRIPT,
        draft_id=draft_id,
    )
    corpus = StubCorpusProvider(entries=[final_entry, everything_entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="EVERYTHING",
            runtime_identity=RuntimeIndexIdentity(
                embedding_model_fingerprint="model_v1",
                chunking_policy_id="policy_v1",
            ),
        )

        results = diagnoser.diagnose()
        assert len(results) == 1
        assert results[0].entry_id == draft_id
        assert results[0].status == SliceStatus.MISSING


def test_diagnose_everything_missing_stale_healthy_unavailable() -> None:
    draft_id = "draft:head:D1:T1"
    entry = _make_entry(
        "D1",
        draft_id,
        "Transcript v1",
        view=CorpusView.EVERYTHING,
        kind=CorpusEntryKind.TRANSCRIPT,
        draft_id=draft_id,
    )
    error_entry = CorpusEntry(
        ref=CorpusEntryRef(
            view=CorpusView.EVERYTHING,
            entry_id="draft:head:D1:T2",
            kind=CorpusEntryKind.TRANSCRIPT,
            dossier_id="D1",
            transcription_id="T2",
            draft_id="draft:head:D1:T2",
        ),
        text="",
        content_hash=None,
        provenance={"error": "missing"},
    )
    corpus = StubCorpusProvider(entries=[entry, error_entry])

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "metadata.db"
        store = VectorMetadataStore(db_path)

        runtime_identity = RuntimeIndexIdentity(
            embedding_model_fingerprint="model_v1",
            chunking_policy_id="policy_v1",
        )

        diagnoser = SliceDiagnoser(
            corpus_provider=corpus,
            metadata_store=store,
            pool_identifier="EVERYTHING",
            runtime_identity=runtime_identity,
        )

        results = {d.entry_id: d for d in diagnoser.diagnose()}
        assert results[draft_id].status == SliceStatus.MISSING
        assert results[draft_id].reason == DiagnosticReasonCode.MISSING_INDEX_STATE.value
        assert results["draft:head:D1:T2"].status == SliceStatus.UNAVAILABLE
        assert (
            results["draft:head:D1:T2"].reason
            == DiagnosticReasonCode.UNAVAILABLE_HYDRATION_FAILED.value
        )

        store.upsert_indexed_entry_state(
            pool_identifier="EVERYTHING",
            dossier_id="D1",
            entry_id=draft_id,
            indexed_signature="stale_signature",
            embedding_model_fingerprint=runtime_identity.embedding_model_fingerprint,
            chunking_policy_id=runtime_identity.chunking_policy_id,
        )

        results = {d.entry_id: d for d in diagnoser.diagnose()}
        assert results[draft_id].status == SliceStatus.STALE_CONTENT
        assert results[draft_id].reason == DiagnosticReasonCode.STALE_SIGNATURE_MISMATCH.value

        store.upsert_indexed_entry_state(
            pool_identifier="EVERYTHING",
            dossier_id="D1",
            entry_id=draft_id,
            indexed_signature=entry.content_hash or "",
            embedding_model_fingerprint=runtime_identity.embedding_model_fingerprint,
            chunking_policy_id=runtime_identity.chunking_policy_id,
        )

        results = {d.entry_id: d for d in diagnoser.diagnose()}
        assert results[draft_id].status == SliceStatus.HEALTHY
