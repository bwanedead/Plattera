"""Tests for continuity_journal mechanical helpers.

Focus areas:
  - _bound_outputs_for_continuity: cap raise, structured-dict fallback, extreme-fallback
  - build_kernel_step_result_record: run-16 regression (3 drafts × ~2450 chars)
  - _clip_large_text_fields: recursive clipping behavior
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from .continuity_journal import (
    CLIP_SENTINEL_KEY,
    _MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS,
    _STRUCTURED_CLIP_FIELD_CHARS,
    _bound_outputs_for_continuity,
    _clip_large_text_fields,
    build_kernel_step_result_record,
)


# ---------------------------------------------------------------------------
# _clip_large_text_fields
# ---------------------------------------------------------------------------


def test_clip_short_string_unchanged() -> None:
    result = _clip_large_text_fields("hello", max_chars=100)
    assert result == "hello"


def test_clip_long_string_returns_sentinel_dict() -> None:
    """Oversized strings must be replaced with a sentinel dict, not a trimmed string.

    The sentinel carries CLIP_SENTINEL_KEY=True, the original char length, and an
    excerpt.  This lets tool_result_slices emit is_complete=False with the true
    original length rather than treating the excerpt as a complete field.
    """
    long_str = "x" * 3000
    result = _clip_large_text_fields(long_str, max_chars=200)
    assert isinstance(result, dict), f"Expected sentinel dict; got {type(result).__name__}"
    assert result.get(CLIP_SENTINEL_KEY) is True
    assert result["original_char_length"] == 3000
    assert result["excerpt"] == "x" * 200


def test_clip_dict_recurses_into_values() -> None:
    data = {"short": "ok", "long": "y" * 3000}
    result = _clip_large_text_fields(data, max_chars=100)
    assert result["short"] == "ok"
    long_val = result["long"]
    assert isinstance(long_val, dict), "Oversized value must become a sentinel dict"
    assert long_val.get(CLIP_SENTINEL_KEY) is True
    assert long_val["original_char_length"] == 3000
    assert long_val["excerpt"] == "y" * 100


def test_clip_list_recurses_into_elements() -> None:
    data = ["a" * 500, "b"]
    result = _clip_large_text_fields(data, max_chars=50)
    assert result[1] == "b"
    clipped = result[0]
    assert isinstance(clipped, dict), "Oversized list element must become a sentinel dict"
    assert clipped.get(CLIP_SENTINEL_KEY) is True
    assert clipped["original_char_length"] == 500
    assert clipped["excerpt"] == "a" * 50


def test_clip_nested_dict_list_structure() -> None:
    data = {"results": [{"text": "z" * 5000}, {"text": "short"}]}
    result = _clip_large_text_fields(data, max_chars=200)
    clipped_text = result["results"][0]["text"]
    assert isinstance(clipped_text, dict), "Nested oversized string must become a sentinel dict"
    assert clipped_text.get(CLIP_SENTINEL_KEY) is True
    assert clipped_text["original_char_length"] == 5000
    assert result["results"][1]["text"] == "short"


def test_clip_non_string_scalars_pass_through() -> None:
    data = {"count": 42, "flag": True, "ratio": 3.14}
    result = _clip_large_text_fields(data, max_chars=5)
    assert result == data


# ---------------------------------------------------------------------------
# _bound_outputs_for_continuity — within-cap path
# ---------------------------------------------------------------------------


def test_bound_small_outputs_returns_dict_not_truncated() -> None:
    outputs = {"status": "ok", "value": 123}
    stored, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=32000)
    assert not truncated
    assert isinstance(stored, dict)
    assert stored["status"] == "ok"


def test_bound_within_cap_roundtrips_cleanly() -> None:
    outputs = {"text": "hello world", "count": 5}
    stored, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=1000)
    assert not truncated
    assert stored["text"] == "hello world"
    assert stored["count"] == 5


# ---------------------------------------------------------------------------
# _bound_outputs_for_continuity — run-16 regression
# ---------------------------------------------------------------------------

_DRAFT_TEXT = (
    "This is a metes and bounds deed description for a parcel of land. "
    "Beginning at a point on the north line of Section Two (2), Township "
    "Four (4) North, Range Three (3) West, thence South 89 degrees 42 "
    "minutes 15 seconds East along the north boundary of said section for "
    "a distance of 660.00 feet to the point of beginning; thence continuing "
    "South 89 degrees 42 minutes 15 seconds East for a distance of 330.00 "
    "feet; thence South 0 degrees 17 minutes 45 seconds West for a distance "
    "of 495.00 feet; thence North 89 degrees 42 minutes 15 seconds West for "
    "330.00 feet; thence North 0 degrees 17 minutes 45 seconds East for "
    "495.00 feet to the point of beginning, containing 3.75 acres more or "
    "less as surveyed by licensed surveyor John Doe on January 15, 2024."
)
# Each draft is ~740 chars; multiply to reach ~2960 chars so 3 drafts → ~9500 chars JSON > 8192 old cap
_DRAFT_TEXT_RUN16 = _DRAFT_TEXT * 4  # ~2960 chars


def _make_run16_outputs() -> dict[str, Any]:
    """3-draft hydrate shape matching run-16 turn 1 outputs (~8453 chars total JSON)."""
    return {
        "t0:raw:draft_1": {"text": _DRAFT_TEXT_RUN16, "source": "llm", "model": "gpt-4o-mini"},
        "t0:raw:draft_2": {"text": _DRAFT_TEXT_RUN16, "source": "llm", "model": "gpt-4o-mini"},
        "t0:raw:draft_3": {"text": _DRAFT_TEXT_RUN16, "source": "llm", "model": "gpt-4o-mini"},
    }


def test_run16_outputs_fit_within_raised_cap() -> None:
    """3-draft hydrate (run-16 shape) must fit within the raised 32000-char cap."""
    outputs = _make_run16_outputs()
    raw_size = len(json.dumps(outputs, ensure_ascii=False, default=str, sort_keys=True))
    # Verify the outputs are actually larger than the old 8192 cap
    assert raw_size > 8192, f"Run-16 fixture must exceed old cap; got {raw_size} chars"
    # But must fit within the new cap
    assert raw_size < _MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS, (
        f"Run-16 fixture ({raw_size} chars) must fit within new cap "
        f"({_MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS})"
    )


def test_run16_bound_returns_complete_dict_not_truncated() -> None:
    """Regression: run-16 outputs must be stored as a complete dict, not a string prefix."""
    outputs = _make_run16_outputs()
    stored, truncated = _bound_outputs_for_continuity(
        outputs, max_json_chars=_MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS
    )
    assert not truncated, "Run-16 outputs must not be flagged as truncated under new cap"
    assert isinstance(stored, dict), (
        "Run-16 outputs must be stored as a dict, not a string prefix; "
        f"got {type(stored).__name__}"
    )
    assert "t0:raw:draft_1" in stored
    assert "t0:raw:draft_2" in stored
    assert "t0:raw:draft_3" in stored


def test_run16_stored_dict_preserves_text_field() -> None:
    """Text fields in stored run-16 outputs must survive round-trip intact."""
    outputs = _make_run16_outputs()
    stored, truncated = _bound_outputs_for_continuity(
        outputs, max_json_chars=_MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS
    )
    assert not truncated
    draft1 = stored.get("t0:raw:draft_1", {})
    assert isinstance(draft1, dict), "Draft 1 must be a dict"
    text = draft1.get("text", "")
    assert len(text) > 100, "Draft 1 text must be preserved"
    assert "Section Two" in text


# ---------------------------------------------------------------------------
# _bound_outputs_for_continuity — oversized path: field-clip preferred over string prefix
# ---------------------------------------------------------------------------


def _make_oversized_outputs(cap: int = 32000) -> dict[str, Any]:
    """Outputs whose JSON exceeds cap — achieved with many large text fields."""
    # Each field ~3000 chars; 15 fields = ~45000 chars JSON
    return {f"field_{i}": "x" * 3000 for i in range(15)}


def test_oversized_outputs_return_dict_not_string() -> None:
    """When outputs exceed cap, _bound must return a dict (field-clipped) not a string prefix."""
    outputs = _make_oversized_outputs()
    stored, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=32000)
    assert truncated, "Oversized outputs must set truncated=True"
    assert isinstance(stored, dict), (
        "Oversized outputs must return a field-clipped dict, not a string; "
        f"got {type(stored).__name__}"
    )


def test_oversized_dict_fields_are_clip_sentinels() -> None:
    """Returned dict field values must be sentinel dicts (not trimmed strings) when clipped."""
    outputs = _make_oversized_outputs()
    stored, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=32000)
    assert truncated
    assert isinstance(stored, dict)
    # At least some fields should be replaced with sentinel dicts
    sentinel_fields = [
        v for v in stored.values()
        if isinstance(v, dict) and v.get(CLIP_SENTINEL_KEY) is True
    ]
    assert sentinel_fields, "At least one field should be a clip sentinel when outputs are oversized"
    # Sentinel must carry original_char_length
    for sentinel in sentinel_fields:
        assert "original_char_length" in sentinel
        assert sentinel["original_char_length"] == 3000  # matches _make_oversized_outputs


def test_oversized_dict_keys_are_all_present() -> None:
    """All top-level keys must survive even when values are clipped.

    Uses 3 fields × 3000-char values: raw ~9300 chars, clipped (2000 each) ~6150 chars.
    cap=8000 sits between raw and clipped sizes so the structured-clip path is taken.
    """
    outputs = {f"field_{i}": "x" * 3000 for i in range(3)}
    stored, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=8000)
    assert truncated
    assert isinstance(stored, dict), (
        f"Expected dict from field-clip path; got {type(stored).__name__}. "
        "Check that clipped JSON fits within the cap."
    )
    for key in outputs:
        assert key in stored, f"Key {key!r} must survive field clipping"


def test_extreme_oversized_falls_back_to_string_prefix() -> None:
    """When even the field-clipped dict exceeds cap, fall back to a string prefix."""
    # 500 keys × 2010-char value → even clipped (2000 chars each) won't fit in 500 chars
    outputs = {f"k{i}": "z" * 3000 for i in range(500)}
    stored, truncated = _bound_outputs_for_continuity(outputs, max_json_chars=500)
    assert truncated
    assert isinstance(stored, str), (
        "Extreme fallback must return a string prefix; got dict — cap was probably too loose"
    )
    assert len(stored) <= 500


# ---------------------------------------------------------------------------
# build_kernel_step_result_record — run-16 integration
# ---------------------------------------------------------------------------


def test_build_record_run16_not_result_truncated() -> None:
    """Regression: build_kernel_step_result_record must not set result_truncated for run-16 outputs."""
    outputs = _make_run16_outputs()
    record = build_kernel_step_result_record(
        kernel_turn_index=1,
        action_type="hydrate_refs",
        execution_state="executed",
        execution_reason_code=None,
        latest_refs_snapshot={"t0:raw:draft_1": {}, "t0:raw:draft_2": {}, "t0:raw:draft_3": {}},
        outputs=outputs,
        artifact_refs=["t0:raw:draft_1", "t0:raw:draft_2", "t0:raw:draft_3"],
    )
    assert record["result_truncated"] is False, (
        "Run-16 shaped outputs must not be marked truncated after the cap raise"
    )
    stored = record["outputs_for_continuity"]
    assert isinstance(stored, dict), f"outputs_for_continuity must be dict; got {type(stored).__name__}"
    assert "t0:raw:draft_1" in stored


def test_build_record_has_expected_shape() -> None:
    """build_kernel_step_result_record must include all expected keys."""
    record = build_kernel_step_result_record(
        kernel_turn_index=5,
        action_type="some_action",
        execution_state="executed",
        execution_reason_code=None,
        latest_refs_snapshot={"ref1": {}},
        outputs={"result": "value"},
        artifact_refs=["ref1"],
    )
    required_keys = {
        "kernel_turn_index",
        "action_type",
        "execution_state",
        "execution_reason_code",
        "artifact_refs",
        "latest_refs_snapshot",
        "outputs_for_continuity",
        "result_truncated",
    }
    assert required_keys.issubset(set(record.keys()))
    assert record["kernel_turn_index"] == 5
    assert record["action_type"] == "some_action"


def test_new_default_cap_is_32000() -> None:
    """Confirm the module-level constant matches the intended value."""
    assert _MAX_OUTPUTS_FOR_CONTINUITY_JSON_CHARS == 32000


def test_structured_clip_field_chars_is_2000() -> None:
    """Confirm per-field clip constant matches the intended value."""
    assert _STRUCTURED_CLIP_FIELD_CHARS == 2000
