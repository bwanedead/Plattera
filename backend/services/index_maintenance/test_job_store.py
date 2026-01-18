from __future__ import annotations

from pathlib import Path

from .job_models import (
    IndexMaintenanceJob,
    IndexMaintenanceJobRequest,
    IndexMaintenanceJobStatus,
    IndexMaintenanceProgress,
    IndexMaintenanceRuntimeIdentity,
    IndexMaintenanceSliceResult,
)
from .job_store import IndexMaintenanceJobStore


def test_job_store_roundtrip(tmp_path: Path) -> None:
    store = IndexMaintenanceJobStore(store_root=tmp_path)

    request = IndexMaintenanceJobRequest(
        pool_identifier="FINAL_SEGMENTS",
        mode="missing_only",
        limit=10,
        dossier_id="D1",
        dry_run=False,
    )
    identity = IndexMaintenanceRuntimeIdentity(
        embedding_model_fingerprint="embed:v1",
        chunking_policy_id="final_segments_v1",
    )
    job = IndexMaintenanceJob.new(request=request, identity=identity)
    store.create(job)

    progress = IndexMaintenanceProgress(total=2, done=1, ok=1, failed=0)
    result = IndexMaintenanceSliceResult(
        dossier_id="D1",
        entry_id="segment_final:D1:seg_001:T1",
        status="healthy",
        reason_code=None,
        detail=None,
    )
    store.update_fields(
        job.id,
        status=IndexMaintenanceJobStatus.RUNNING.value,
        progress=progress.__dict__,
        results=[result.__dict__],
    )

    reloaded = store.get(job.id)
    assert reloaded is not None
    assert reloaded["id"] == job.id
    assert reloaded["request"]["pool_identifier"] == "FINAL_SEGMENTS"
    assert reloaded["identity"]["embedding_model_fingerprint"] == "embed:v1"
    assert reloaded["status"] == IndexMaintenanceJobStatus.RUNNING.value
    assert reloaded["progress"]["done"] == 1
    assert reloaded["results"][0]["entry_id"] == "segment_final:D1:seg_001:T1"

    index_path = tmp_path / "jobs_index.json"
    assert index_path.exists()
