"""Tests for inbound user-message normalization + size bounds."""

from __future__ import annotations

from harness.runtime.user_messages.message_shape import (
    clamp_defer_reason,
    normalize_user_message,
)


# ---------------------------------------------------------------------------
# Sparse output: only fields present in input appear in output
# ---------------------------------------------------------------------------

def test_short_text_passes_through_unchanged() -> None:
    out = normalize_user_message({"text": "hello agent"})
    assert out == {"text": "hello agent"}
    assert "_bounds" not in out


def test_full_payload_passes_through() -> None:
    out = normalize_user_message({
        "message_id": "user-msg-abc",
        "created_at_epoch_seconds": 1000,
        "source": "cli",
        "text": "do the thing",
        "metadata": {"item_id": "i-1"},
    })
    assert out["message_id"] == "user-msg-abc"
    assert out["created_at_epoch_seconds"] == 1000
    assert out["source"] == "cli"
    assert out["text"] == "do the thing"
    assert out["metadata"] == {"item_id": "i-1"}
    assert "_bounds" not in out


def test_unknown_extra_fields_dropped() -> None:
    out = normalize_user_message({"text": "x", "random_field": "drop"})
    assert "random_field" not in out


def test_non_mapping_input_returns_empty_dict() -> None:
    assert normalize_user_message(None) == {}
    assert normalize_user_message("string") == {}
    assert normalize_user_message([1, 2, 3]) == {}


# ---------------------------------------------------------------------------
# text bounds (8,192 char cap)
# ---------------------------------------------------------------------------

def test_long_text_truncated_with_marker() -> None:
    long = "x" * 20_000
    out = normalize_user_message({"text": long})
    assert len(out["text"]) == 8_192
    assert out["_bounds"] == {"text_truncated": True}


def test_non_string_text_coerced() -> None:
    out = normalize_user_message({"text": 42})
    assert out["text"] == "42"


def test_null_text_becomes_empty_string() -> None:
    out = normalize_user_message({"text": None})
    assert out["text"] == ""


# ---------------------------------------------------------------------------
# metadata bounds (32,768 JSON char cap)
# ---------------------------------------------------------------------------

def test_small_metadata_unchanged() -> None:
    out = normalize_user_message({"metadata": {"k": "v"}})
    assert out["metadata"] == {"k": "v"}


def test_large_metadata_replaced_with_stub() -> None:
    out = normalize_user_message({"metadata": {"blob": "z" * 50_000}})
    md = out["metadata"]
    assert md.get("_truncated") is True
    assert len(md.get("_prefix") or "") == 32_768
    assert out["_bounds"]["metadata_truncated"] is True


def test_non_dict_metadata_becomes_empty() -> None:
    out = normalize_user_message({"metadata": "not-a-dict"})
    assert out["metadata"] == {}


# ---------------------------------------------------------------------------
# message_id and source bounds
# ---------------------------------------------------------------------------

def test_long_message_id_truncated() -> None:
    out = normalize_user_message({"message_id": "user-msg-" + "a" * 300})
    assert len(out["message_id"]) == 256
    assert out["_bounds"]["message_id_truncated"] is True


def test_long_source_truncated() -> None:
    out = normalize_user_message({"source": "s" * 100})
    assert len(out["source"]) == 64
    assert out["_bounds"]["source_truncated"] is True


def test_blank_message_id_dropped() -> None:
    """Whitespace-only message_id is treated as absent."""
    out = normalize_user_message({"message_id": "   "})
    assert "message_id" not in out


# ---------------------------------------------------------------------------
# created_at_epoch_seconds preservation
# ---------------------------------------------------------------------------

def test_int_timestamp_preserved() -> None:
    out = normalize_user_message({"created_at_epoch_seconds": 1234})
    assert out["created_at_epoch_seconds"] == 1234


def test_float_timestamp_preserved() -> None:
    out = normalize_user_message({"created_at_epoch_seconds": 1234.5})
    assert out["created_at_epoch_seconds"] == 1234.5


def test_bool_timestamp_dropped() -> None:
    """bool is a subclass of int but is not a valid timestamp."""
    out = normalize_user_message({"created_at_epoch_seconds": True})
    assert "created_at_epoch_seconds" not in out


# ---------------------------------------------------------------------------
# Re-normalization preserves admission-time _bounds markers
# ---------------------------------------------------------------------------

def test_re_normalization_preserves_existing_bounds() -> None:
    """Defensive re-normalization must not erase prior truncation markers."""
    first = normalize_user_message({"text": "x" * 20_000})
    assert first["_bounds"] == {"text_truncated": True}
    second = normalize_user_message(first)
    assert second["_bounds"]["text_truncated"] is True


def test_unknown_bounds_keys_dropped() -> None:
    """Adversarial _bounds keys outside the canonical set must not survive."""
    out = normalize_user_message({
        "text": "ok",
        "_bounds": {"text_truncated": True, "evil_marker": True, "x" * 5_000: True},
    })
    assert out["_bounds"] == {"text_truncated": True}


# ---------------------------------------------------------------------------
# defer reason clamp
# ---------------------------------------------------------------------------

def test_clamp_defer_reason_short_passes_through() -> None:
    assert clamp_defer_reason("not actionable yet") == "not actionable yet"


def test_clamp_defer_reason_strips_whitespace() -> None:
    assert clamp_defer_reason("  hold for hitl  ") == "hold for hitl"


def test_clamp_defer_reason_empty_returns_none() -> None:
    assert clamp_defer_reason("") is None
    assert clamp_defer_reason("   ") is None
    assert clamp_defer_reason(None) is None


def test_clamp_defer_reason_long_truncated() -> None:
    long = "x" * 1_000
    assert len(clamp_defer_reason(long)) == 400


def test_clamp_defer_reason_non_string_returns_none() -> None:
    assert clamp_defer_reason(42) is None
    assert clamp_defer_reason(["a"]) is None
