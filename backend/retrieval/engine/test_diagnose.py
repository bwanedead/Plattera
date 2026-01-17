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


def _make_entry(dossier_id: str, entry_id: str, text: str) -> CorpusEntry:
    ref = CorpusEntryRef(
        view=CorpusView.FINAL_SEGMENTS,
        entry_id=entry_id,
        kind=CorpusEntryKind.SEGMENT_FINAL_TEXT,
        dossier_id=dossier_id,
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
