"""Tests for generic upstream run lineage contract."""

from __future__ import annotations

import pytest

from harness.runtime.upstream_run_lineage import (
    UPSTREAM_RUN_LINEAGE_LAUNCH_KEY,
    UpstreamRunLineageError,
    normalize_upstream_run_lineage,
    partition_launch_context_for_upstream_lineage,
)


def _valid_lineage(*, extra_run: dict | None = None) -> dict:
    rows = [
        {
            "run_id": "practice-row-live-20260619-76",
            "domain_id": "transcript_edit",
            "relation": "input_handoff",
            "handoff_refs": [
                "transcript_edit:output",
                "transcript_edit:resolution_state:practice-row-live-20260619-76",
            ],
        }
    ]
    if extra_run is not None:
        rows.append(extra_run)
    return {
        "schema_version": "upstream_run_lineage.v1",
        "upstream_runs": rows,
    }


def test_normalize_upstream_run_lineage_preserves_exact_ref_values() -> None:
    normalized = normalize_upstream_run_lineage(_valid_lineage())
    assert normalized["upstream_runs"][0]["handoff_refs"] == [
        "transcript_edit:output",
        "transcript_edit:resolution_state:practice-row-live-20260619-76",
    ]


def test_normalize_upstream_run_lineage_accepts_multiple_rows() -> None:
    normalized = normalize_upstream_run_lineage(
        _valid_lineage(
            extra_run={
                "run_id": "upstream-run-02",
                "domain_id": "deed_to_ir",
                "relation": "prior_attempt",
                "handoff_refs": ["deed_to_ir:output"],
            }
        )
    )
    assert len(normalized["upstream_runs"]) == 2


def test_partition_launch_context_strips_reserved_key() -> None:
    launch = {
        "run_id": "downstream-run",
        UPSTREAM_RUN_LINEAGE_LAUNCH_KEY: _valid_lineage(),
        "model": "gpt-5.4-mini",
    }
    lineage, domain_context = partition_launch_context_for_upstream_lineage(launch)
    assert lineage is not None
    assert UPSTREAM_RUN_LINEAGE_LAUNCH_KEY not in domain_context
    assert domain_context["run_id"] == "downstream-run"


def test_normalize_rejects_unsafe_run_id_path_characters() -> None:
    bad = _valid_lineage()
    bad["upstream_runs"][0]["run_id"] = "../practice-row-live"
    with pytest.raises(UpstreamRunLineageError, match="run_id_unsafe"):
        normalize_upstream_run_lineage(bad)


def test_normalize_rejects_too_many_upstream_rows() -> None:
    rows = []
    for idx in range(9):
        rows.append(
            {
                "run_id": f"run-{idx}",
                "domain_id": "transcript_edit",
                "relation": "input_handoff",
                "handoff_refs": ["transcript_edit:output"],
            }
        )
    with pytest.raises(UpstreamRunLineageError, match="too_many"):
        normalize_upstream_run_lineage(
            {"schema_version": "upstream_run_lineage.v1", "upstream_runs": rows}
        )


def test_normalize_accepts_artifact_ref_with_slashes() -> None:
    lineage = _valid_lineage()
    artifact_ref = "artifact://dossiers/9f5eecb6-cd7e-483c-b691-b76aa7132e8e/mappings/clean.png"
    lineage["upstream_runs"][0]["handoff_refs"].append(artifact_ref)
    normalized = normalize_upstream_run_lineage(lineage)
    assert artifact_ref in normalized["upstream_runs"][0]["handoff_refs"]


def test_normalize_rejects_handoff_ref_control_characters() -> None:
    bad = _valid_lineage()
    bad["upstream_runs"][0]["handoff_refs"] = ["transcript_edit:output\ninjected"]
    with pytest.raises(UpstreamRunLineageError, match="control_character"):
        normalize_upstream_run_lineage(bad)


def test_normalize_rejects_handoff_ref_backticks_for_timeline_rendering() -> None:
    bad = _valid_lineage()
    bad["upstream_runs"][0]["handoff_refs"] = ["transcript_edit:`output`"]
    with pytest.raises(UpstreamRunLineageError, match="unrenderable"):
        normalize_upstream_run_lineage(bad)


def test_normalize_rejects_missing_schema_version() -> None:
    with pytest.raises(UpstreamRunLineageError, match="schema_version"):
        normalize_upstream_run_lineage({"upstream_runs": _valid_lineage()["upstream_runs"]})
