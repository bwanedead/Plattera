"""Tests for Agent Kernel run artifact persistence."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# Direct import to avoid triggering backend/services/__init__.py side effects.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "services" / "agent_kernel"))

from backend.agent_kernel.models import ActionType
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, StepRecord
from backend.config.paths import agent_kernel_artifacts_root
from run_artifact_persistence_service import RunArtifactPersistenceService


def _build_run_artifact(run_id: str, request_id: str) -> RunArtifact:
    return RunArtifact(
        run_id=run_id,
        request_id=request_id,
        ir_artifact_ref=ArtifactRef(artifact_path="artifacts/ir/ir-001.json"),
        compile_artifact_ref=ArtifactRef(artifact_path="artifacts/compile/compile-001.json"),
        steps=[
            StepRecord(
                step_id="step-001",
                action=ActionType.COMPILE,
                inputs={"input_ref": "artifacts/ir/ir-001.json"},
                outputs={"compile_artifact_ref": {"artifact_path": "artifacts/compile/compile-001.json"}},
            )
        ],
    )


def test_save_run_artifact_writes_atomically_and_updates_index(tmp_path: Path) -> None:
    service = RunArtifactPersistenceService(
        root=tmp_path / "agent-kernel-artifacts",
        state_dir=tmp_path / "state",
    )

    run_artifact = _build_run_artifact(run_id="run-001", request_id="req-001")
    result = service.save_run_artifact(run_artifact)

    artifact_path = Path(result["path"])
    index_path = tmp_path / "state" / "agent_kernel_runs_index.json"
    assert result["success"] is True
    assert artifact_path.exists()
    assert index_path.exists()

    with artifact_path.open("r", encoding="utf-8") as file_obj:
        payload = json.load(file_obj)
    assert payload["run_id"] == "run-001"
    assert payload["request_id"] == "req-001"

    with index_path.open("r", encoding="utf-8") as file_obj:
        index_payload = json.load(file_obj)
    assert len(index_payload["runs"]) == 1
    assert index_payload["runs"][0]["run_id"] == "run-001"
    assert index_payload["runs"][0]["request_id"] == "req-001"
    assert index_payload["runs"][0]["artifact_path"] == str(artifact_path)


def test_index_deduplicates_same_request_and_run(tmp_path: Path) -> None:
    service = RunArtifactPersistenceService(
        root=tmp_path / "agent-kernel-artifacts",
        state_dir=tmp_path / "state",
    )

    run_artifact = _build_run_artifact(run_id="run-001", request_id="req-001")
    service.save_run_artifact(run_artifact)
    service.save_run_artifact(run_artifact)

    index_entries = service.list_run_artifacts()
    assert len(index_entries) == 1
    assert index_entries[0]["run_id"] == "run-001"
    assert index_entries[0]["request_id"] == "req-001"


def test_get_and_list_run_artifacts_filter_by_request(tmp_path: Path) -> None:
    service = RunArtifactPersistenceService(
        root=tmp_path / "agent-kernel-artifacts",
        state_dir=tmp_path / "state",
    )

    first = _build_run_artifact(run_id="run-001", request_id="req-001")
    second = _build_run_artifact(run_id="run-002", request_id="req-002")
    service.save_run_artifact(first)
    service.save_run_artifact(second)

    loaded = service.get_run_artifact(request_id="req-001", run_id="run-001")
    assert loaded is not None
    assert loaded.run_id == "run-001"
    assert loaded.request_id == "req-001"

    req_one_entries = service.list_run_artifacts(request_id="req-001")
    assert len(req_one_entries) == 1
    assert req_one_entries[0]["run_id"] == "run-001"


def test_agent_kernel_artifacts_root_is_dedicated_subtree() -> None:
    root = agent_kernel_artifacts_root()
    assert root.name == "agent_kernel"
    assert "artifacts" in root.parts
