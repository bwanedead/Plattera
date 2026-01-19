from __future__ import annotations

from pathlib import Path

import asyncio
from fastapi import BackgroundTasks

from retrieval.engine.diagnose import RuntimeIndexIdentity
from retrieval.engine.pool_maintenance import (
    PoolBootstrapReport,
    PoolBootstrapStatus,
    PoolOpenReport,
    PoolOpenResult,
    PoolOpenStatus,
)
from retrieval.engine.reason_codes import DiagnosticReasonCode
from retrieval.lanes.semantic.metadata_store import VectorMetadataStore
from services.index_maintenance import IndexMaintenanceJobStatus

from api.endpoints import index_maintenance as endpoint


def test_execute_bootstraps_missing_artifacts(tmp_path: Path, monkeypatch) -> None:
    identity = RuntimeIndexIdentity(
        embedding_model_fingerprint="embed:v1",
        chunking_policy_id="final_segments_v1",
    )
    job_identity = endpoint.IndexMaintenanceRuntimeIdentity(
        embedding_model_fingerprint="embed:v1",
        chunking_policy_id="final_segments_v1",
    )
    monkeypatch.setattr(
        endpoint,
        "_resolve_runtime_identity",
        lambda _pool: (identity, None, job_identity),
    )

    store_root = tmp_path / "jobs"
    monkeypatch.setattr(
        "services.index_maintenance.job_store.dossiers_processing_jobs_root",
        lambda _job_type: store_root,
    )

    metadata_path = tmp_path / "metadata.db"
    metadata_store = VectorMetadataStore(metadata_path)

    class StubStore:
        def __init__(self):
            self.metadata_store = metadata_store

    calls = {"open": 0, "bootstrap": 0}

    def _safe_open(_pool):
        calls["open"] += 1
        if calls["open"] == 1:
            return PoolOpenResult(
                report=PoolOpenReport(
                    status=PoolOpenStatus.UNAVAILABLE,
                    reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                    detail="missing_files:metadata.db",
                    action_hint=None,
                )
            )
        return PoolOpenResult(
            report=PoolOpenReport(status=PoolOpenStatus.OK, reason_code=None),
            store=StubStore(),
        )

    def _bootstrap(**kwargs):
        calls["bootstrap"] += 1
        return PoolBootstrapReport(
            pool_identifier=kwargs["pool_identifier"],
            status=PoolBootstrapStatus.CREATED,
            reason_code=None,
            detail=None,
            action_hint=None,
        )

    monkeypatch.setattr(endpoint, "safe_open_pool", _safe_open)
    monkeypatch.setattr(endpoint, "bootstrap_pool_artifacts", _bootstrap)
    monkeypatch.setattr(endpoint, "_collect_slice_diagnoses", lambda **_kwargs: [])

    background = BackgroundTasks()
    payload = endpoint.ExecuteRequest(
        pool_identifier="FINAL_SEGMENTS",
        mode="missing_only",
        limit=5,
        dry_run=True,
    )
    response = asyncio.run(endpoint.execute_index(payload, background))

    assert response["status"] == IndexMaintenanceJobStatus.SUCCEEDED.value
    assert calls["bootstrap"] == 1
    assert calls["open"] == 2
