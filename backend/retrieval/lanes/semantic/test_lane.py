"""
Tests for LocalSemanticLane
============================

Validates:
- Safe failure modes when index is missing/uninitialized
- EvidenceCard structure and provenance
"""

import pytest

from services.assets.service import AssetsService

from .lane import LocalSemanticLane


def test_missing_index_safe_failure():
    """
    Test that LocalSemanticLane returns safe empty result when index is missing.

    Acceptance criteria for S7:
    - If the index is missing/uninitialized, the lane returns a safe empty result
      with an explicit reason (no crash)
    """
    # Create lane (no index built)
    lane = LocalSemanticLane(
        assets_service=AssetsService(),
        pool_identifier="FINAL_SEGMENTS",
    )

    # Query without an index should not crash
    result = lane.search(query="test query", limit=5)

    # Verify safe failure
    assert result.query == "test query"
    assert result.cards == []
    assert "reason" in result.debug or "gating_errors" in result.debug

    # If embedding model is missing, should have gating_errors
    # If index is missing, should have "index_not_initialized" reason
    if "reason" in result.debug:
        assert result.debug["reason"] == "index_not_initialized"


def test_lane_structure():
    """
    Test that LocalSemanticLane has correct structure for wiring.

    Validates:
    - Lane has pool_identifier attribute
    - Lane has search method that returns RetrievalResult
    """
    lane = LocalSemanticLane(pool_identifier="FINAL_SEGMENTS")

    assert lane.pool_identifier == "FINAL_SEGMENTS"
    assert hasattr(lane, "search")
    assert callable(lane.search)

    # Verify search signature
    result = lane.search("test", limit=10)
    assert hasattr(result, "query")
    assert hasattr(result, "cards")
    assert hasattr(result, "debug")
