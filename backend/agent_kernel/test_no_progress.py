"""Tests for deterministic no-progress detection helpers."""

from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.models import StopReason
from backend.agent_kernel.no_progress import (
    GapSignal,
    NoProgressDetector,
    build_iteration_fingerprint,
    compute_artifact_digests,
    compute_gap_signature,
)
from backend.agent_kernel.policies import FeatureGraphDeedToMapPolicyV0
from backend.agent_kernel.run_artifact import ArtifactRef


def test_compute_gap_signature_is_deterministic_for_policy_weighted_gaps() -> None:
    policy = FeatureGraphDeedToMapPolicyV0()
    gaps = [
        GapSignal(gap_code="validation_failure", base_score=2.0),
        GapSignal(gap_code="global_anchor_missing", base_score=1.0),
    ]

    signature_a = compute_gap_signature(gaps, policy)
    signature_b = compute_gap_signature(list(reversed(gaps)), policy)

    assert signature_a == signature_b
    assert len(signature_a) == 64


def test_compute_artifact_digests_changes_when_refs_change() -> None:
    iteration_one = compute_artifact_digests(
        {
            "ir": ArtifactRef(artifact_path="artifacts/ir/ir-001.json"),
            "judge": "artifacts/judge/judge-001.json",
            "bundle": None,
        }
    )
    iteration_two = compute_artifact_digests(
        {
            "ir": ArtifactRef(artifact_path="artifacts/ir/ir-002.json"),
            "judge": "artifacts/judge/judge-001.json",
            "bundle": None,
        }
    )

    assert iteration_one["ir"] != iteration_two["ir"]
    assert iteration_one["judge"] == iteration_two["judge"]
    assert set(iteration_one.keys()) == {"bundle", "ir", "judge"}


def test_no_progress_detector_returns_stop_reason_after_n_stagnant_repairs() -> None:
    detector = NoProgressDetector(max_stagnant_repair_cycles=2)
    gap_signature = "gap-signature"
    artifact_digests = {"ir": "digest-ir", "judge": "digest-judge"}

    first = detector.evaluate_repair_cycle(
        gap_signature=gap_signature,
        artifact_digests=artifact_digests,
    )
    second = detector.evaluate_repair_cycle(
        gap_signature=gap_signature,
        artifact_digests=artifact_digests,
    )
    third = detector.evaluate_repair_cycle(
        gap_signature=gap_signature,
        artifact_digests=artifact_digests,
    )

    assert first.detected is False
    assert second.detected is False
    assert third.detected is True
    assert third.stop_reason == StopReason.NO_PROGRESS
    assert third.reason_code == "no_progress_repair_cycles_exhausted"
    assert third.stagnant_repair_cycles == 2


def test_iteration_fingerprint_changes_with_gap_or_artifact_changes() -> None:
    base = build_iteration_fingerprint(
        gap_signature="gap-a",
        artifact_digests={"compile": "compile-a", "ir": "ir-a"},
    )
    changed_gap = build_iteration_fingerprint(
        gap_signature="gap-b",
        artifact_digests={"compile": "compile-a", "ir": "ir-a"},
    )
    changed_artifacts = build_iteration_fingerprint(
        gap_signature="gap-a",
        artifact_digests={"compile": "compile-b", "ir": "ir-a"},
    )

    assert base != changed_gap
    assert base != changed_artifacts
