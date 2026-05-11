"""Tests for inbound HITL feedback normalization + size bounds.

Pins the per-field truncation behavior and the ``_bounds`` truncation marker
shape so downstream consumers (ledger, trace, prompt projection, audit) can
detect clipped feedback.
"""

from __future__ import annotations

import json

import pytest

from harness.runtime.hitl.feedback_shape import normalize_hitl_feedback


# ---------------------------------------------------------------------------
# choice bounds
# ---------------------------------------------------------------------------

def test_short_choice_passes_through_unchanged() -> None:
    out = normalize_hitl_feedback({"choice": "yes"})
    assert out == {"choice": "yes"}
    assert "_bounds" not in out


def test_long_choice_is_truncated_and_marked() -> None:
    long_choice = "x" * 20_000
    out = normalize_hitl_feedback({"choice": long_choice})
    assert len(out["choice"]) == 16_384
    assert out["_bounds"] == {"choice_truncated": True}


def test_null_choice_preserved_as_none() -> None:
    out = normalize_hitl_feedback({"choice": None})
    assert out == {"choice": None}


def test_non_string_choice_coerced_to_string() -> None:
    out = normalize_hitl_feedback({"choice": 42})
    assert out["choice"] == "42"
    assert "_bounds" not in out


# ---------------------------------------------------------------------------
# note bounds
# ---------------------------------------------------------------------------

def test_short_note_passes_through_unchanged() -> None:
    out = normalize_hitl_feedback({"note": "looks good"})
    assert out == {"note": "looks good"}
    assert "_bounds" not in out


def test_long_note_is_truncated_and_marked() -> None:
    long_note = "y" * 50_000
    out = normalize_hitl_feedback({"note": long_note})
    assert len(out["note"]) == 16_384
    assert out["_bounds"]["note_truncated"] is True


def test_non_string_note_dropped_to_none() -> None:
    out = normalize_hitl_feedback({"note": ["not", "a", "string"]})
    assert out["note"] is None


# ---------------------------------------------------------------------------
# metadata bounds (JSON-char bounded)
# ---------------------------------------------------------------------------

def test_small_metadata_passes_through_unchanged() -> None:
    md = {"k1": "v1", "k2": 42}
    out = normalize_hitl_feedback({"metadata": md})
    assert out["metadata"] == md
    assert "_bounds" not in out


def test_large_metadata_replaced_by_truncated_stub() -> None:
    # Build a metadata blob whose JSON serialization clearly exceeds 32_768 chars.
    big_value = "z" * 50_000
    out = normalize_hitl_feedback({"metadata": {"huge": big_value}})
    md = out["metadata"]
    assert md.get("_truncated") is True
    assert isinstance(md.get("_prefix"), str)
    assert len(md["_prefix"]) == 32_768
    assert out["_bounds"]["metadata_truncated"] is True


def test_metadata_with_unserializable_values_falls_back_to_stub() -> None:
    """Pathological metadata (cycles, non-JSON types) fall back to a stub.

    ``json.dumps(default=str)`` handles most cases by stringifying, but a true
    failure must still produce a truncated stub rather than raise.
    """
    class BadObj:
        def __repr__(self):
            raise RuntimeError("unprintable")
    # default=str inside json.dumps will call str() which calls repr() for many
    # types; the explicit cycle below is more reliable.
    cyclic: dict = {}
    cyclic["self"] = cyclic
    out = normalize_hitl_feedback({"metadata": cyclic})
    md = out["metadata"]
    assert md.get("_truncated") is True
    assert out["_bounds"]["metadata_truncated"] is True


def test_non_dict_metadata_replaced_with_empty() -> None:
    out = normalize_hitl_feedback({"metadata": "not-a-dict"})
    assert out["metadata"] == {}


# ---------------------------------------------------------------------------
# prompt_id, submitted_at_epoch_seconds, sparse output
# ---------------------------------------------------------------------------

def test_prompt_id_preserved_when_in_bounds() -> None:
    out = normalize_hitl_feedback({"prompt_id": "p-123"})
    assert out["prompt_id"] == "p-123"


def test_long_prompt_id_truncated_and_marked() -> None:
    long_pid = "p-" + "a" * 300
    out = normalize_hitl_feedback({"prompt_id": long_pid})
    assert len(out["prompt_id"]) == 256
    assert out["_bounds"]["prompt_id_truncated"] is True


def test_submitted_at_epoch_seconds_preserved() -> None:
    out = normalize_hitl_feedback({"submitted_at_epoch_seconds": 1234.5})
    assert out["submitted_at_epoch_seconds"] == 1234.5


def test_unknown_extra_fields_dropped() -> None:
    """Canonical inbound shape is fixed — unknown fields don't enter ledger."""
    out = normalize_hitl_feedback({
        "choice": "yes",
        "random_field": "should be dropped",
        "another": [1, 2, 3],
    })
    assert "random_field" not in out
    assert "another" not in out


def test_output_is_sparse_only_present_keys_emitted() -> None:
    """Absent fields are NOT filled with default None — keep ledger entries lean."""
    out = normalize_hitl_feedback({"choice": "yes"})
    assert "note" not in out
    assert "metadata" not in out
    assert "prompt_id" not in out
    assert "submitted_at_epoch_seconds" not in out


def test_non_mapping_input_returns_empty_dict() -> None:
    assert normalize_hitl_feedback(None) == {}
    assert normalize_hitl_feedback("string") == {}
    assert normalize_hitl_feedback([1, 2, 3]) == {}


# ---------------------------------------------------------------------------
# combined bounds — multiple truncations on one payload
# ---------------------------------------------------------------------------

def test_multiple_field_truncations_all_marked_in_bounds() -> None:
    out = normalize_hitl_feedback({
        "choice": "c" * 20_000,
        "note": "n" * 20_000,
        "metadata": {"big": "m" * 50_000},
    })
    bounds = out["_bounds"]
    assert bounds["choice_truncated"] is True
    assert bounds["note_truncated"] is True
    assert bounds["metadata_truncated"] is True


# ---------------------------------------------------------------------------
# Idempotency on already-normalized payloads
# ---------------------------------------------------------------------------

def test_normalize_is_idempotent_on_already_normalized() -> None:
    """Defensive normalization in record_inbound must not alter already-bounded data."""
    once = normalize_hitl_feedback({"choice": "ok", "note": "fine", "metadata": {"k": "v"}})
    twice = normalize_hitl_feedback(once)
    assert twice == once


def test_normalize_preserves_existing_bounds_markers_through_second_pass() -> None:
    """When re-normalizing already-clipped data, prior _bounds flags must survive.

    Otherwise the defensive re-normalization in ``record_inbound`` would silently
    erase truncation markers from data already bounded at admission by
    ``hitl_poll_feedback_store``.
    """
    # First pass: large choice produces truncation marker.
    first = normalize_hitl_feedback({"choice": "c" * 30_000, "note": "ok"})
    assert first["_bounds"] == {"choice_truncated": True}

    # Second pass: input is already clipped — no new truncation, but marker
    # must be carried forward.
    second = normalize_hitl_feedback(first)
    assert "_bounds" in second
    assert second["_bounds"]["choice_truncated"] is True


def test_normalize_merges_old_and_new_bounds() -> None:
    """If a second pass introduces additional truncation, both old and new markers persist."""
    # Simulate a pre-existing _bounds block (e.g. from upstream normalizer).
    seeded = {
        "choice": "ok",  # not truncated this pass
        "note": "n" * 30_000,  # WILL be truncated this pass
        "_bounds": {"metadata_truncated": True},  # carried in
    }
    out = normalize_hitl_feedback(seeded)
    assert out["_bounds"]["metadata_truncated"] is True   # preserved
    assert out["_bounds"]["note_truncated"] is True       # newly set


def test_normalize_drops_false_or_invalid_bounds_keys() -> None:
    """Only truthy boolean markers from the canonical key set are carried forward."""
    out = normalize_hitl_feedback({
        "choice": "ok",
        "_bounds": {"choice_truncated": False, "note_truncated": "yes", 42: True, "metadata_truncated": True},
    })
    bounds = out.get("_bounds", {})
    # False markers dropped, non-bool truthy values dropped, non-string keys dropped
    assert bounds == {"metadata_truncated": True}


def test_normalize_drops_unknown_bounds_keys_to_prevent_payload_smuggling() -> None:
    """Adversarial _bounds keys (outside the canonical set) must NOT survive.

    Regression: prior implementation accepted any string key with value True,
    which would let a malformed inbound payload smuggle arbitrary keys into
    durable ledger state and defeat the payload-bounding goal.
    """
    adversarial_bounds = {
        # Canonical — should survive
        "choice_truncated": True,
        # All of these are unknown and must be dropped
        "evil_marker": True,
        "huge_blob_field": True,
        "x" * 5_000: True,  # large key
        "internal_debug": True,
        "operator_override": True,
    }
    out = normalize_hitl_feedback({"choice": "ok", "_bounds": adversarial_bounds})
    bounds = out["_bounds"]
    assert bounds == {"choice_truncated": True}, (
        f"Only canonical markers should survive; got {bounds!r}"
    )


def test_normalize_drops_oversized_bounds_object_entirely() -> None:
    """A huge _bounds dict with no canonical keys yields no _bounds at all."""
    huge_bounds = {f"unknown_key_{i}": True for i in range(10_000)}
    out = normalize_hitl_feedback({"choice": "ok", "_bounds": huge_bounds})
    # No canonical markers AND no new truncation this pass → no _bounds key emitted
    assert "_bounds" not in out


def test_normalize_ignores_non_mapping_bounds() -> None:
    out = normalize_hitl_feedback({"choice": "ok", "_bounds": "not-a-mapping"})
    assert "_bounds" not in out
