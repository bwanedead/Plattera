from __future__ import annotations

from pathlib import Path

import asyncio
import pytest
from fastapi import BackgroundTasks, HTTPException

from retrieval.engine.diagnose import RuntimeIndexIdentity, SliceDiagnosis, SliceStatus
from retrieval.engine.pool_maintenance import (
    PoolBootstrapReport,
    PoolBootstrapStatus,
    PoolMaintenanceReport,
    PoolOpenReport,
    PoolOpenResult,
    PoolOpenStatus,
)
from retrieval.engine.reason_codes import DiagnosticReasonCode
from retrieval.lanes.semantic.metadata_store import VectorMetadataStore
from services.index_maintenance import IndexMaintenanceJobStore

from api.endpoints import index_maintenance as endpoint


def test_diagnose_identity_failure_returns_unavailable(monkeypatch) -> None:

    report = PoolOpenReport(
        status=PoolOpenStatus.UNAVAILABLE,
        reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
        detail="RuntimeError",
        action_hint=None,
    )

    monkeypatch.setattr(
        endpoint,
        "_resolve_runtime_identity",
        lambda _pool: (None, report, None),
    )

    data = asyncio.run(endpoint.diagnose_index(pool_identifier="FINAL_SEGMENTS"))
    assert data["pool_open"]["status"] == PoolOpenStatus.UNAVAILABLE.value
    assert data["pool_open"]["reason_code"] == DiagnosticReasonCode.UNAVAILABLE_UNKNOWN.value


def test_diagnose_limits_slices(monkeypatch) -> None:

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

    slices = [
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D2",
            entry_id="A",
            status=SliceStatus.MISSING,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="B",
            status=SliceStatus.STALE_CONTENT,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="A",
            status=SliceStatus.HEALTHY,
        ),
    ]

    class StubController:
        def __init__(self, *_args, **_kwargs):
            pass

        def diagnose_pool(self, **_kwargs):
            return PoolMaintenanceReport(
                pool_identifier="FINAL_SEGMENTS",
                pool_open=PoolOpenReport(
                    status=PoolOpenStatus.OK,
                    reason_code=None,
                ),
                pool_health=None,
                slice_diagnoses=slices,
            )

    monkeypatch.setattr(endpoint, "PoolMaintenanceController", StubController)

    data = asyncio.run(
        endpoint.diagnose_index(
            pool_identifier="FINAL_SEGMENTS",
            include_slices=True,
            limit_slices=1,
        )
    )
    assert len(data["slice_diagnoses"]) == 1
    assert data["counts"]["missing"] == 1
    assert data["counts"]["stale"] == 1
    assert data["counts"]["healthy"] == 1


def test_select_slices_orders_and_limits() -> None:
    diagnoses = [
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D2",
            entry_id="B",
            status=SliceStatus.MISSING,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="C",
            status=SliceStatus.STALE_CONTENT,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="A",
            status=SliceStatus.MISSING,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="B",
            status=SliceStatus.HEALTHY,
        ),
    ]

    selected = endpoint._select_slices(diagnoses, "missing_and_stale", 2)
    assert [d.entry_id for d in selected] == ["A", "C"]


def test_select_slices_prune_orphans() -> None:
    diagnoses = [
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="A",
            status=SliceStatus.ORPHANED,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="B",
            status=SliceStatus.MISSING,
        ),
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D2",
            entry_id="C",
            status=SliceStatus.ORPHANED,
        ),
    ]

    selected = endpoint._select_slices(diagnoses, "prune_orphans", 10)
    assert [d.entry_id for d in selected] == ["A", "C"]


def test_execute_creates_job_record(tmp_path: Path, monkeypatch) -> None:

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

    open_result = PoolOpenResult(
        report=PoolOpenReport(status=PoolOpenStatus.OK, reason_code=None),
        store=StubStore(),
    )

    monkeypatch.setattr(endpoint, "safe_open_pool", lambda _pool: open_result)
    monkeypatch.setattr(endpoint, "_collect_slice_diagnoses", lambda **_kwargs: [
        SliceDiagnosis(
            pool_identifier="FINAL_SEGMENTS",
            dossier_id="D1",
            entry_id="A",
            status=SliceStatus.MISSING,
        )
    ])
    monkeypatch.setattr(endpoint, "_run_job", lambda **_kwargs: None)

    background = BackgroundTasks()
    payload = endpoint.ExecuteRequest(
        pool_identifier="FINAL_SEGMENTS",
        mode="missing_only",
        limit=500,
        dry_run=True,
    )
    response = asyncio.run(endpoint.execute_index(payload, background))
    job_id = response["job_id"]

    store = IndexMaintenanceJobStore(store_root=store_root)
    job = store.get(job_id)
    assert job is not None
    assert job["request"]["limit"] == endpoint.MAX_EXECUTE_LIMIT


def test_get_job_404(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "services.index_maintenance.job_store.dossiers_processing_jobs_root",
        lambda _job_type: tmp_path,
    )
    with pytest.raises(HTTPException) as excinfo:
        asyncio.run(endpoint.get_index_job("does-not-exist"))
    assert excinfo.value.status_code == 404


def test_bootstrap_single_pool(monkeypatch) -> None:
    report = PoolBootstrapReport(
        pool_identifier="FINAL_SEGMENTS",
        status=PoolBootstrapStatus.NEEDS_FORCE_REPAIR,
        reason_code=DiagnosticReasonCode.UNAVAILABLE_NEEDS_FORCE_REPAIR,
        detail="missing_files:metadata.db",
        action_hint="FORCE_REPAIR",
    )
    monkeypatch.setattr(
        endpoint,
        "bootstrap_pool_artifacts",
        lambda **_kwargs: report,
    )
    monkeypatch.setattr(
        endpoint,
        "safe_open_pool",
        lambda _pool: PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.UNAVAILABLE,
                reason_code=DiagnosticReasonCode.UNAVAILABLE_UNKNOWN,
                detail="missing_files:metadata.db",
                action_hint=None,
            )
        ),
    )

    payload = endpoint.BootstrapRequest(pool_identifier="FINAL_SEGMENTS", force=True)
    data = asyncio.run(endpoint.bootstrap_index(payload))
    assert data["results"][0]["pool_identifier"] == "FINAL_SEGMENTS"
    assert data["results"][0]["bootstrap"]["status"] == PoolBootstrapStatus.NEEDS_FORCE_REPAIR.value
    assert (
        data["results"][0]["bootstrap"]["reason_code"]
        == DiagnosticReasonCode.UNAVAILABLE_NEEDS_FORCE_REPAIR.value
    )


def test_bootstrap_all_pools(monkeypatch) -> None:
    calls = []

    def _bootstrap(**kwargs):
        calls.append(kwargs["pool_identifier"])
        return PoolBootstrapReport(
            pool_identifier=kwargs["pool_identifier"],
            status=PoolBootstrapStatus.CREATED,
            reason_code=None,
            detail=None,
            action_hint=None,
        )

    monkeypatch.setattr(endpoint, "bootstrap_pool_artifacts", _bootstrap)
    monkeypatch.setattr(
        endpoint,
        "safe_open_pool",
        lambda _pool: PoolOpenResult(
            report=PoolOpenReport(
                status=PoolOpenStatus.OK,
                reason_code=None,
                detail=None,
                action_hint=None,
            )
        ),
    )

    payload = endpoint.BootstrapRequest()
    data = asyncio.run(endpoint.bootstrap_index(payload))
    assert set(calls) == {"FINAL_SEGMENTS", "EVERYTHING"}
    assert {item["pool_identifier"] for item in data["results"]} == {
        "FINAL_SEGMENTS",
        "EVERYTHING",
    }
