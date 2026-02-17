"""Tests for policy interface and default deed-to-map policy scaffold."""

from __future__ import annotations

from pathlib import Path
import sys

# Ensure repo root is importable when pytest is invoked from any cwd.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.models import ActionType, KernelState
from backend.agent_kernel.policies import FeatureGraphDeedToMapPolicyV0, KernelPolicy


def test_policy_interface_exposes_required_hooks() -> None:
    assert hasattr(KernelPolicy, "routing_order")
    assert hasattr(KernelPolicy, "score_gap")


def test_default_policy_provides_deterministic_routing_order() -> None:
    policy = FeatureGraphDeedToMapPolicyV0()
    ordered = policy.routing_order(
        state=KernelState.HAVE_IR,
        available_actions=[
            ActionType.JUDGE,
            ActionType.RETRIEVE_EVIDENCE,
            ActionType.COMPILE,
        ],
    )

    assert ordered == (
        ActionType.RETRIEVE_EVIDENCE,
        ActionType.COMPILE,
        ActionType.JUDGE,
    )


def test_default_policy_scores_gaps_with_weights() -> None:
    policy = FeatureGraphDeedToMapPolicyV0()

    assert policy.score_gap("global_anchor_missing", 2.0) == 4.0
    assert policy.score_gap("unknown_gap", 2.0) == 2.0
    assert policy.score_gap("unknown_gap", -5.0) == 0.0
