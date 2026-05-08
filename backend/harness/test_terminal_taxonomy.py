"""Unit tests for terminal_taxonomy classify_terminal_artifact_posture."""

from __future__ import annotations

import pytest

from harness.terminal_taxonomy import classify_terminal_artifact_posture


# ---------------------------------------------------------------------------
# completed_with_output
# ---------------------------------------------------------------------------


def test_completed_with_output_ref_key() -> None:
    posture = classify_terminal_artifact_posture("completed", ["transcript_edit:output"])
    assert posture == "completed_with_output"


def test_completed_with_multiple_refs_including_output() -> None:
    posture = classify_terminal_artifact_posture(
        "completed", ["working:rev:0001", "transcript_edit:output"]
    )
    assert posture == "completed_with_output"


def test_completed_non_output_non_working_ref_returns_none() -> None:
    # Evidence/source refs like dossier:schema:v1 are neither output nor working tier.
    posture = classify_terminal_artifact_posture("completed", ["dossier:schema:v1"])
    assert posture is None


# ---------------------------------------------------------------------------
# completed_with_working_artifact
# ---------------------------------------------------------------------------


def test_completed_working_only_ref() -> None:
    posture = classify_terminal_artifact_posture("completed", ["working:rev:0001"])
    assert posture == "completed_with_working_artifact"


def test_completed_multiple_working_only_refs() -> None:
    posture = classify_terminal_artifact_posture(
        "completed", ["working:rev:0001", "working:rev:0002"]
    )
    assert posture == "completed_with_working_artifact"


def test_completed_no_refs_returns_none() -> None:
    posture = classify_terminal_artifact_posture("completed", [])
    assert posture is None


# ---------------------------------------------------------------------------
# blocked_with_working_artifact
# ---------------------------------------------------------------------------


def test_blocked_with_working_ref() -> None:
    posture = classify_terminal_artifact_posture("blocked", ["working:rev:0001"])
    assert posture == "blocked_with_working_artifact"


def test_waiting_human_with_working_ref() -> None:
    posture = classify_terminal_artifact_posture("waiting_human", ["working:rev:0001"])
    assert posture == "blocked_with_working_artifact"


def test_exhausted_with_working_ref() -> None:
    posture = classify_terminal_artifact_posture("exhausted", ["working:rev:0003"])
    assert posture == "blocked_with_working_artifact"


def test_blocked_no_refs_returns_none() -> None:
    posture = classify_terminal_artifact_posture("blocked", [])
    assert posture is None


# ---------------------------------------------------------------------------
# failed_or_recoverable_error
# ---------------------------------------------------------------------------


def test_failed_always_error_posture() -> None:
    posture = classify_terminal_artifact_posture("failed", ["working:rev:0001"])
    assert posture == "failed_or_recoverable_error"


def test_stopped_always_error_posture() -> None:
    posture = classify_terminal_artifact_posture("stopped", [])
    assert posture == "failed_or_recoverable_error"


def test_paused_always_error_posture() -> None:
    posture = classify_terminal_artifact_posture("paused", ["transcript_edit:output"])
    assert posture == "failed_or_recoverable_error"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_none_terminal_class_returns_none() -> None:
    posture = classify_terminal_artifact_posture(None, ["transcript_edit:output"])
    assert posture is None


def test_empty_string_keys_ignored() -> None:
    posture = classify_terminal_artifact_posture("completed", ["", "working:rev:0001"])
    assert posture == "completed_with_working_artifact"


def test_working_prefix_detection_is_prefix_only() -> None:
    # "notworking:artifact" is not a working ref AND does not end with ":output" → None
    posture = classify_terminal_artifact_posture("completed", ["notworking:artifact"])
    assert posture is None


def test_evidence_refs_do_not_count_as_output() -> None:
    # image:derived:*, t0:artifact:*, source:* are evidence/source — not final output
    for ref_key in ["image:derived:0001", "t0:artifact:0001", "source:abc"]:
        posture = classify_terminal_artifact_posture("completed", [ref_key])
        assert posture is None, f"Expected None for evidence ref {ref_key!r}, got {posture!r}"


def test_output_requires_colon_output_suffix() -> None:
    # ":output" suffix is required — ":outputs" or "output" alone don't qualify
    posture = classify_terminal_artifact_posture("completed", ["transcript_edit:outputs"])
    assert posture is None
    posture2 = classify_terminal_artifact_posture("completed", ["output"])
    assert posture2 is None


def test_run13_real_shape_classified_correctly() -> None:
    # Run 13 actual keys: image:derived:* evidence + transcript_edit:working segment refs
    refs = ["image:derived:0001", "transcript_edit:working", "transcript_edit:working:rev:0001"]
    posture = classify_terminal_artifact_posture("completed", refs)
    assert posture == "completed_with_working_artifact"


def test_working_ref_colon_working_suffix() -> None:
    # key.endswith(":working") — transcript_edit:working
    posture = classify_terminal_artifact_posture("completed", ["transcript_edit:working"])
    assert posture == "completed_with_working_artifact"


def test_working_ref_colon_working_colon_segment() -> None:
    # ":working:" in key — transcript_edit:working:rev:0001
    posture = classify_terminal_artifact_posture("completed", ["transcript_edit:working:rev:0001"])
    assert posture == "completed_with_working_artifact"


def test_working_ref_exact_working_key() -> None:
    posture = classify_terminal_artifact_posture("completed", ["working"])
    assert posture == "completed_with_working_artifact"


def test_run16_complete_run_with_only_working_refs_is_working_artifact_not_output() -> None:
    """Run-16 regression: complete_run with only working refs must NOT be completed_with_output.

    In run-16 the loop exited via complete_run with refs that were all working-tier
    (no `:output` suffix).  The correct posture is `completed_with_working_artifact`.
    This test pins that completed + working-only refs ≠ completed_with_output.
    """
    working_refs = [
        "transcript_edit:working",
        "transcript_edit:working:rev:0023",
    ]
    posture = classify_terminal_artifact_posture("completed", working_refs)
    assert posture == "completed_with_working_artifact", (
        f"Expected completed_with_working_artifact for working-only refs; got {posture!r}"
    )
    assert posture != "completed_with_output"
