"""Tests for the agent-authored ``hydrate_next`` helper module."""

from __future__ import annotations

from typing import Any

import pytest

from harness.runtime.orchestration.hydrate_next import (
    HYDRATE_ARTIFACT_REFS_ACTION_ID,
    MAX_HYDRATE_NEXT_REFS,
    HydrateNextValidationError,
    build_hydrate_next_record,
    build_tool_result_snapshot,
    normalize_hydrate_next,
    normalize_hydrate_next_reason,
    resolve_hydrate_next_refs,
    validate_stored_hydrate_next_record,
)


# ---------------------------------------------------------------------------
# normalize_hydrate_next
# ---------------------------------------------------------------------------

def test_normalize_hydrate_next_none_returns_empty_no_errors() -> None:
    refs, errors = normalize_hydrate_next(None)
    assert refs == []
    assert errors == []


def test_normalize_hydrate_next_accepts_literal_refs() -> None:
    refs, errors = normalize_hydrate_next(["transcript_edit:working:rev:0001", "artifact://x"])
    assert refs == ["transcript_edit:working:rev:0001", "artifact://x"]
    assert errors == []


def test_normalize_hydrate_next_accepts_placeholders() -> None:
    refs, errors = normalize_hydrate_next([
        "@result.derived_ref_id", "@result.revision_ref",
        "@result.published_ref", "@result.artifact_refs[]",
    ])
    assert refs == [
        "@result.derived_ref_id", "@result.revision_ref",
        "@result.published_ref", "@result.artifact_refs[]",
    ]
    assert errors == []


def test_normalize_hydrate_next_dedupes_preserving_order() -> None:
    refs, _ = normalize_hydrate_next(["a", "b", "a", "c"])
    assert refs == ["a", "b", "c"]


def test_normalize_hydrate_next_rejects_non_list() -> None:
    with pytest.raises(HydrateNextValidationError, match="must be a JSON array"):
        normalize_hydrate_next("a,b,c")  # type: ignore[arg-type]


def test_normalize_hydrate_next_surfaces_non_string_entries_as_errors() -> None:
    refs, errors = normalize_hydrate_next(["a", 42, "b"])  # type: ignore[list-item]
    assert refs == ["a", "b"]
    assert any(e["reason_code"] == "non_string_entry" for e in errors)


def test_normalize_hydrate_next_skips_blank_entries() -> None:
    refs, errors = normalize_hydrate_next(["a", "   ", "b"])
    assert refs == ["a", "b"]
    assert any(e["reason_code"] == "blank_entry" for e in errors)


def test_normalize_hydrate_next_rejects_overlong_refs() -> None:
    """Refs are identifiers — silent truncation would change the target."""
    long_ref = "x" * 500
    with pytest.raises(HydrateNextValidationError, match="exceeds"):
        normalize_hydrate_next([long_ref])


def test_normalize_hydrate_next_rejects_list_over_max() -> None:
    with pytest.raises(HydrateNextValidationError, match="exceeds max length"):
        normalize_hydrate_next([f"ref-{i}" for i in range(MAX_HYDRATE_NEXT_REFS + 1)])


# ---------------------------------------------------------------------------
# normalize_hydrate_next_reason
# ---------------------------------------------------------------------------

def test_normalize_hydrate_next_reason_none() -> None:
    assert normalize_hydrate_next_reason(None) is None


def test_normalize_hydrate_next_reason_blank_becomes_none() -> None:
    assert normalize_hydrate_next_reason("   ") is None


def test_normalize_hydrate_next_reason_text_is_kept() -> None:
    assert normalize_hydrate_next_reason("inspect saved") == "inspect saved"


def test_normalize_hydrate_next_reason_clamps_overlong() -> None:
    out = normalize_hydrate_next_reason("x" * 800)
    assert len(out or "") == 400


def test_normalize_hydrate_next_reason_rejects_non_string() -> None:
    with pytest.raises(HydrateNextValidationError):
        normalize_hydrate_next_reason(42)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# resolve_hydrate_next_refs — placeholders + literal refs
# ---------------------------------------------------------------------------

def test_resolve_literal_refs_pass_through_without_tool_result() -> None:
    resolved, errors = resolve_hydrate_next_refs(["artifact://x"], tool_result=None)
    assert resolved == ["artifact://x"]
    assert errors == []


def test_resolve_derived_ref_id_from_outputs() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@result.derived_ref_id"],
        tool_result={"outputs": {"derived_ref_id": "transcript_edit:derived:abc"}},
    )
    assert resolved == ["transcript_edit:derived:abc"]
    assert errors == []


def test_resolve_this_result_derived_ref_id() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@this.result.derived_ref_id"],
        tool_result={"outputs": {"derived_ref_id": "image:derived:crop-a"}},
    )
    assert resolved == ["image:derived:crop-a"]
    assert errors == []
    assert "@result.result" not in str(errors)


def test_resolve_this_result_artifact_refs_list() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@this.result.artifact_refs[]"],
        tool_result={"artifact_refs": ["image:derived:a", "image:derived:b"]},
    )
    assert resolved == ["image:derived:a", "image:derived:b"]
    assert errors == []


def test_resolve_four_rows_each_this_result_derived_ref() -> None:
    snapshots = {
        f"crop_{i}": {
            "outputs": {"derived_ref_id": f"image:derived:crop-{i}"},
            "artifact_refs": [],
        }
        for i in range(4)
    }
    resolved_all: list[str] = []
    errors_all: list[dict[str, Any]] = []
    for alias, snap in snapshots.items():
        resolved, errors = resolve_hydrate_next_refs(
            ["@this.result.derived_ref_id"],
            tool_result=snap,
        )
        for row in errors:
            tagged = dict(row)
            tagged["action_alias"] = alias
            errors_all.append(tagged)
        for ref in resolved:
            if ref not in resolved_all:
                resolved_all.append(ref)
    assert resolved_all == [f"image:derived:crop-{i}" for i in range(4)]
    assert errors_all == []


def test_resolve_bad_placeholder_preserves_other_rows() -> None:
    good, good_err = resolve_hydrate_next_refs(
        ["@this.result.derived_ref_id"],
        tool_result={"outputs": {"derived_ref_id": "image:derived:ok"}},
    )
    bad, bad_err = resolve_hydrate_next_refs(
        ["@this.result.what_is_this"],
        tool_result={"outputs": {}},
    )
    assert good == ["image:derived:ok"]
    assert good_err == []
    assert bad == []
    assert len(bad_err) == 1
    assert bad_err[0]["reason_code"] == "unknown_placeholder"
    assert "@result.result.derived_ref_id" not in str(bad_err)


def test_resolve_revision_ref_from_outputs() -> None:
    resolved, _ = resolve_hydrate_next_refs(
        ["@result.revision_ref"],
        tool_result={"outputs": {"revision_ref": "transcript_edit:working:rev:0001"}},
    )
    assert resolved == ["transcript_edit:working:rev:0001"]


def test_resolve_published_ref_from_outputs() -> None:
    resolved, _ = resolve_hydrate_next_refs(
        ["@result.published_ref"],
        tool_result={"outputs": {"published_ref": "transcript_edit:published:1"}},
    )
    assert resolved == ["transcript_edit:published:1"]


def test_resolve_artifact_refs_list_from_top_level() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@result.artifact_refs[]"],
        tool_result={"artifact_refs": ["a", "b", "c"]},
    )
    assert resolved == ["a", "b", "c"]
    assert errors == []


def test_resolve_artifact_refs_list_caps_at_max() -> None:
    refs = [f"r-{i}" for i in range(10)]
    resolved, _ = resolve_hydrate_next_refs(
        ["@result.artifact_refs[]"],
        tool_result={"artifact_refs": refs},
    )
    assert len(resolved) == MAX_HYDRATE_NEXT_REFS


def test_resolve_unknown_placeholder_surfaces_compact_error() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@result.what_is_this"], tool_result={"outputs": {}},
    )
    assert resolved == []
    assert errors == [{"requested_ref": "@result.what_is_this", "reason_code": "unknown_placeholder"}]


def test_resolve_missing_placeholder_surfaces_compact_error() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@result.revision_ref"], tool_result={"outputs": {}},
    )
    assert resolved == []
    assert errors == [{"requested_ref": "@result.revision_ref", "reason_code": "placeholder_not_found"}]


def test_resolve_missing_artifact_refs_list_surfaces_error() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@result.artifact_refs[]"], tool_result={"artifact_refs": []},
    )
    assert resolved == []
    assert errors[0]["reason_code"] == "placeholder_not_found"


def test_resolve_dedupes_in_order_across_literals_and_placeholders() -> None:
    resolved, _ = resolve_hydrate_next_refs(
        ["a", "@result.revision_ref", "a", "b"],
        tool_result={"outputs": {"revision_ref": "b"}},
    )
    # 'a' once, then 'b' once (revision_ref resolves to 'b', explicit 'b' deduped)
    assert resolved == ["a", "b"]


# ---------------------------------------------------------------------------
# build_hydrate_next_record + validator round-trip
# ---------------------------------------------------------------------------

def test_build_record_has_pending_status_and_no_hydrated_results() -> None:
    rec = build_hydrate_next_record(
        requested_refs=["@result.revision_ref"],
        resolved_refs=["transcript_edit:working:rev:0001"],
        reason="inspect saved payload",
        errors=[],
        source_turn_index=41,
    )
    assert rec["status"] == "pending"
    assert rec["hydrated_results"] is None
    assert rec["surfaced_iteration"] is None
    assert rec["source_turn_index"] == 41
    assert rec["resolved_refs"] == ["transcript_edit:working:rev:0001"]
    assert rec["reason"] == "inspect saved payload"


def test_validate_stored_record_round_trip() -> None:
    rec = build_hydrate_next_record(
        requested_refs=["a"],
        resolved_refs=["a"],
        reason=None,
        errors=[],
        source_turn_index=2,
    )
    out = validate_stored_hydrate_next_record(rec)
    assert out is not None
    assert out["status"] == "pending"
    assert out["requested_refs"] == ["a"]


def test_validate_stored_rejects_unknown_status() -> None:
    bad = build_hydrate_next_record(
        requested_refs=["a"], resolved_refs=["a"], reason=None, errors=[], source_turn_index=1,
    )
    bad["status"] = "weird"
    assert validate_stored_hydrate_next_record(bad) is None


def test_validate_stored_rejects_negative_source_turn() -> None:
    bad = build_hydrate_next_record(
        requested_refs=["a"], resolved_refs=["a"], reason=None, errors=[], source_turn_index=1,
    )
    bad["source_turn_index"] = -1
    assert validate_stored_hydrate_next_record(bad) is None


def test_validate_stored_accepts_none() -> None:
    assert validate_stored_hydrate_next_record(None) is None


# ---------------------------------------------------------------------------
# build_tool_result_snapshot
# ---------------------------------------------------------------------------

def test_build_tool_result_snapshot_filters_outputs_keys() -> None:
    snap = build_tool_result_snapshot(
        outputs={"revision_ref": "r", "extra_garbage": [1, 2, 3]},
        artifact_refs=("a", "b"),
    )
    assert snap == {"outputs": {"revision_ref": "r"}, "artifact_refs": ["a", "b"]}


def test_build_tool_result_snapshot_handles_none() -> None:
    snap = build_tool_result_snapshot(outputs=None, artifact_refs=None)
    assert snap == {}


# ---------------------------------------------------------------------------
# Canonical tool id constant
# ---------------------------------------------------------------------------

def test_canonical_hydrate_action_id() -> None:
    assert HYDRATE_ARTIFACT_REFS_ACTION_ID == "hydrate_artifact_refs"


# ---------------------------------------------------------------------------
# @batch.* placeholders
# ---------------------------------------------------------------------------

def test_resolve_batch_derived_ref_id() -> None:
    batch = {
        "crop_a": {
            "outputs": {"derived_ref_id": "image:derived:a"},
            "artifact_refs": ["image:derived:a"],
        },
    }
    resolved, errors = resolve_hydrate_next_refs(
        ["@batch.crop_a.result.derived_ref_id"],
        tool_result=None,
        batch_results=batch,
    )
    assert resolved == ["image:derived:a"]
    assert errors == []


def test_resolve_batch_artifact_refs_list() -> None:
    batch = {
        "h1": {"outputs": {}, "artifact_refs": ["r1", "r2"]},
    }
    resolved, errors = resolve_hydrate_next_refs(
        ["@batch.h1.result.artifact_refs[]"],
        tool_result=None,
        batch_results=batch,
    )
    assert resolved == ["r1", "r2"]
    assert errors == []


def test_resolve_batch_unresolved_alias_produces_error() -> None:
    resolved, errors = resolve_hydrate_next_refs(
        ["@batch.missing.result.derived_ref_id"],
        tool_result=None,
        batch_results={},
    )
    assert resolved == []
    assert errors[0]["reason_code"] == "batch_alias_not_found"


def test_resolve_batch_dedupes_with_literals() -> None:
    batch = {"a": {"outputs": {"derived_ref_id": "x"}, "artifact_refs": ["x"]}}
    resolved, _ = resolve_hydrate_next_refs(
        ["x", "@batch.a.result.derived_ref_id"],
        tool_result=None,
        batch_results=batch,
    )
    assert resolved == ["x"]
