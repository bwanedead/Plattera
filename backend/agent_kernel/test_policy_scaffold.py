"""Tests for policy interface and default deed-to-map policy scaffold."""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.models import ActionType, KernelState
from backend.agent_kernel.policies import DefaultKernelPolicy, KernelPolicy
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact, StepRecord, ValidationInline
from backend.feature_graph.kernel_claimability import FeatureGraphClaimabilityPolicy
from backend.feature_graph.kernel_policy import FeatureGraphDeedToMapPolicyV0


def test_policy_interface_exposes_required_hooks() -> None:
    policy = DefaultKernelPolicy()
    assert isinstance(policy, KernelPolicy)


def test_default_policy_provides_deterministic_routing_order() -> None:
    policy = DefaultKernelPolicy()
    ordered = policy.routing_order(
        state=KernelState.SOURCE_READY,
        available_actions=[
            ActionType.JUDGE,
            ActionType.RETRIEVE_EVIDENCE,
            ActionType.COMPILE,
        ],
    )

    assert ordered == (
        ActionType.JUDGE,
        ActionType.RETRIEVE_EVIDENCE,
        ActionType.COMPILE,
    )


def test_default_policy_scores_gaps_with_weights() -> None:
    policy = DefaultKernelPolicy()

    assert policy.score_gap("global_anchor_missing", 2.0) == 2.0
    assert policy.score_gap("unknown_gap", 2.0) == 2.0
    assert policy.score_gap("unknown_gap", -5.0) == 0.0


def test_product_policy_lives_outside_shared_core() -> None:
    policy = FeatureGraphDeedToMapPolicyV0()

    assert policy.score_gap("global_anchor_missing", 2.0) == 4.0


def test_product_claimability_recognizes_canonical_validate_artifact() -> None:
    policy = FeatureGraphClaimabilityPolicy()
    run_artifact = RunArtifact(
        run_id="run-001",
        request_id="req-001",
        ir_artifact_ref=ArtifactRef(artifact_path="artifacts/ir/ir-001.json"),
        compile_artifact_ref=ArtifactRef(artifact_path="artifacts/compile/compile-001.json"),
        judge_artifact_ref=ArtifactRef(artifact_path="artifacts/judge/judge-001.json"),
        georeference_artifact_ref=ArtifactRef(artifact_path="artifacts/georef/georef-001.json"),
        validate_artifact_ref=ArtifactRef(artifact_path="artifacts/validate/validation-001.json"),
        render_artifact_ref=ArtifactRef(artifact_path="artifacts/render/render-001.json"),
        requires_global_placement=True,
        render_required=True,
        steps=[
            StepRecord(
                step_id="step-validate-001",
                action=ActionType.VALIDATE_ARTIFACT,
                validation_result=ValidationInline(passed=True, reason_code="ok", checks={}),
            )
        ],
    )

    claimable, missing = policy.evaluate(run_artifact)

    assert claimable is True
    assert "validation_passed" not in missing
