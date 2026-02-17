"""Tests for Agent Kernel v0 run artifact and step record refs."""

from pathlib import Path
import sys

import pytest
from pydantic import ValidationError

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.models import ActionType
from backend.agent_kernel.run_artifact import (
    ArtifactRef,
    RunArtifact,
    StepRecord,
    ValidationInline,
)


def test_run_artifact_round_trip_stores_refs_for_core_artifacts():
    run_artifact = RunArtifact(
        run_id="run-001",
        request_id="req-001",
        ir_artifact_ref=ArtifactRef(artifact_path="artifacts/ir/ir-001.json"),
        compile_artifact_ref=ArtifactRef(artifact_path="artifacts/compile/compile-001.json"),
        judge_artifact_ref=ArtifactRef(artifact_path="artifacts/judge/judge-001.json"),
        bundle_artifact_ref=ArtifactRef(artifact_path="artifacts/bundle/bundle-001.json"),
        retrieval_artifact_ref=ArtifactRef(
            artifact_path="artifacts/retrieval/retrieval-001.json",
            card_index=2,
            span_index=7,
        ),
    )

    payload = run_artifact.model_dump_json()
    rehydrated = RunArtifact.model_validate_json(payload)

    assert rehydrated.run_id == "run-001"
    assert rehydrated.ir_artifact_ref.artifact_path.endswith("ir-001.json")
    assert rehydrated.compile_artifact_ref.artifact_path.endswith("compile-001.json")
    assert rehydrated.judge_artifact_ref.artifact_path.endswith("judge-001.json")
    assert rehydrated.bundle_artifact_ref.artifact_path.endswith("bundle-001.json")
    assert rehydrated.retrieval_artifact_ref.card_index == 2
    assert rehydrated.retrieval_artifact_ref.span_index == 7


def test_step_record_captures_action_inputs_outputs_and_reason_codes():
    step = StepRecord(
        step_id="step-validate-001",
        action=ActionType.VALIDATE,
        inputs={"judge_ref": "artifacts/judge/judge-001.json"},
        outputs={"validation_ref": "inline"},
        reason_codes=["validation_passed"],
        outputs_inline={"summary": "validated", "error_count": 0},
        validation_result=ValidationInline(
            passed=True,
            reason_code="ok",
            checks={"gap_count": 0},
        ),
    )

    payload = step.model_dump_json()
    rehydrated = StepRecord.model_validate_json(payload)

    assert rehydrated.action == ActionType.VALIDATE
    assert rehydrated.inputs["judge_ref"].endswith("judge-001.json")
    assert rehydrated.outputs["validation_ref"] == "inline"
    assert rehydrated.reason_codes == ["validation_passed"]
    assert rehydrated.outputs_inline["error_count"] == 0
    assert rehydrated.validation_result.passed is True
    assert rehydrated.validation_result.reason_code == "ok"


def test_step_record_rejects_large_geometry_blobs_in_outputs_inline():
    large_geometry = {
        "geometry": {
            "coordinates": [[float(i), float(i + 1)] for i in range(200)],
        }
    }

    with pytest.raises(ValidationError):
        StepRecord(
            step_id="step-validate-002",
            action=ActionType.VALIDATE,
            outputs_inline=large_geometry,
        )
