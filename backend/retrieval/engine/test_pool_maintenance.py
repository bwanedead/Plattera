from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set

from corpus.interfaces import CorpusProvider
from corpus.types import CorpusEntry, CorpusEntryKind, CorpusEntryRef, CorpusView

from ..lanes.semantic.manifest import (
    MANIFEST_SCHEMA_VERSION,
    SemanticIndexManifest,
    write_manifest,
)
from ..lanes.semantic.metadata_store import VectorMetadataStore
from .pool_maintenance import (
    ACTION_HINT_REBUILD_POOL,
    PoolMaintenanceController,
    PoolOpenReport,
    PoolOpenResult,
    PoolOpenStatus,
    safe_open_pool,
)
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


def _write_manifest_stub(pool_identifier: str) -> None:
    manifest = SemanticIndexManifest(
        schema_version=MANIFEST_SCHEMA_VERSION,
        pool_identifier=pool_identifier,
        embedding_dim=4,
        embedding_model_id="stub-model",
        chunking_policy_id="stub-policy",
    )
    write_manifest(pool_identifier, manifest)


def test_safe_open_pool_schema_mismatch(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    _write_manifest_stub("TEST_POOL")

    pool_root = tmp_path / "semantic_indexes" / "TEST_POOL"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    (pool_root / "metadata.db").write_text("stub", encoding="utf-8")

    def _raise_schema_mismatch(**_kwargs):
        raise RuntimeError("schema version mismatch")

    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance.load_persistent_store",
        _raise_schema_mismatch,
    )

    result = safe_open_pool("TEST_POOL")
    assert result.report.status == PoolOpenStatus.UNAVAILABLE
    assert result.report.reason_code == DiagnosticReasonCode.UNAVAILABLE_SCHEMA_VERSION_MISMATCH
    assert result.report.action_hint == ACTION_HINT_REBUILD_POOL


def test_safe_open_pool_generic_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("retrieval.lanes.semantic.manifest.assets_root", lambda: tmp_path)
    _write_manifest_stub("TEST_POOL")

    pool_root = tmp_path / "semantic_indexes" / "TEST_POOL"
    (pool_root / "hnsw.bin").write_text("stub", encoding="utf-8")
    (pool_root / "metadata.db").write_text("stub", encoding="utf-8")

    monkeypatch.setattr(
        "retrieval.engine.pool_maintenance.load_persistent_store",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = safe_open_pool("TEST_POOL")
    assert result.report.status == PoolOpenStatus.UNAVAILABLE
    assert result.report.reason_code == DiagnosticReasonCode.UNAVAILABLE_UNKNOWN
    assert result.report.detail == "RuntimeError"


def test_pool_health_report_compaction_toggle(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        metadata_path = Path(tmpdir) / "metadata.db"
        metadata_store = VectorMetadataStore(metadata_path)

        class StubStore:
            def __init__(self):
                self.metadata_store = metadata_store

            def get_stats(self) -> dict:
                return {
                    "active_chunks": 10,
                    "tombstoned_vectors": 5,
                    "tombstone_ratio": 0.33,
                }

            def should_compact(self, threshold: float = 0.3) -> bool:
                return threshold <= 0.2

        store = StubStore()
        ok_report = PoolOpenReport(
            status=PoolOpenStatus.OK,
            reason_code=None,
        )

        monkeypatch.setattr(
            "retrieval.engine.pool_maintenance.safe_open_pool",
            lambda _pool_identifier: PoolOpenResult(report=ok_report, store=store),
        )

        controller = PoolMaintenanceController(corpus_provider=StubCorpusProvider(entries=[]))

        low_threshold_report = controller.diagnose_pool(
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=None,
            compaction_threshold=0.1,
        )
        high_threshold_report = controller.diagnose_pool(
            pool_identifier="FINAL_SEGMENTS",
            runtime_identity=None,
            compaction_threshold=0.9,
        )

        assert low_threshold_report.pool_health is not None
        assert low_threshold_report.pool_health.compact_recommended is True
        assert high_threshold_report.pool_health is not None
        assert high_threshold_report.pool_health.compact_recommended is False
