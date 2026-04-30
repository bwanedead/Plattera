"""Tests for tool_result_slices.py — structural metadata and excerpt-boundary awareness."""
from __future__ import annotations

from harness.runtime.memory.tool_result_slices import (
    _extract_structural_metadata,
    build_recent_tool_result_slices,
    check_outputs_excerpt_truncated,
)


def _result_record(
    turn: int,
    *,
    outputs: object = None,
    result_truncated: bool = False,
    action_type: str = "hydrate_artifact_refs",
    execution_state: str = "executed",
) -> dict:
    return {
        "kernel_turn_index": turn,
        "action_type": action_type,
        "execution_state": execution_state,
        "execution_reason_code": None,
        "result_truncated": result_truncated,
        "artifact_refs": [],
        "outputs_for_continuity": outputs or {},
    }


# ---------------------------------------------------------------------------
# _extract_structural_metadata
# ---------------------------------------------------------------------------


def test_extract_structural_metadata_returns_top_level_keys_for_mapping() -> None:
    outputs = {"status": "ok", "count": 3, "items": []}
    meta = _extract_structural_metadata(outputs)
    assert meta is not None
    assert set(meta["top_level_keys"]) == {"status", "count", "items"}


def test_extract_structural_metadata_returns_none_for_string() -> None:
    meta = _extract_structural_metadata("plain text output")
    assert meta is None


def test_extract_structural_metadata_returns_none_for_none() -> None:
    meta = _extract_structural_metadata(None)
    assert meta is None


def test_extract_structural_metadata_strips_binary_keys() -> None:
    outputs = {"status": "ok", "image_bytes": b"...", "text": "hello"}
    meta = _extract_structural_metadata(outputs)
    assert meta is not None
    assert "image_bytes" not in meta["top_level_keys"]
    assert "status" in meta["top_level_keys"]
    assert "text" in meta["top_level_keys"]


def test_extract_structural_metadata_includes_nested_mapping_keys() -> None:
    outputs = {"status": "ok", "result": {"value": "abc", "confidence": 0.9}}
    meta = _extract_structural_metadata(outputs)
    assert meta is not None
    # Nested result keys should appear under some path
    all_values = [v for v in meta.values() if isinstance(v, list)]
    assert any("value" in v and "confidence" in v for v in all_values)


def test_extract_structural_metadata_traverses_list_of_results_three_levels_deep() -> None:
    """Run-6 failure shape: outputs.results[0].payload.payload contract keys are visible."""
    outputs = {
        "results": [
            {
                "payload": {
                    "payload": {
                        "source_transcript_verbatim": {"text": "..."},
                        "parcel_metadata": {},
                        "issues": [],
                    }
                }
            }
        ]
    }
    meta = _extract_structural_metadata(outputs)
    assert meta is not None
    assert "top_level_keys" in meta
    assert "results" in meta["top_level_keys"]
    # results[0] keys should be present
    assert any("results" in k and "0" in k for k in meta)
    # The deep payload.payload keys must be visible even when excerpt is truncated
    all_values = [v for v in meta.values() if isinstance(v, list)]
    assert any("source_transcript_verbatim" in v for v in all_values), (
        "source_transcript_verbatim not found in any key list — "
        f"traversal did not reach results[0].payload.payload; meta={meta}"
    )
    assert any("parcel_metadata" in v for v in all_values)


def test_extract_structural_metadata_bounded_by_max_paths() -> None:
    """Deeply nested artifacts don't explode the metadata size."""
    def _nest(depth: int) -> dict:
        if depth == 0:
            return {"leaf": "value"}
        return {"payload": _nest(depth - 1)}

    outputs = {"results": [_nest(10)]}
    meta = _extract_structural_metadata(outputs)
    assert meta is not None
    assert len(meta) <= 10  # _MAX_TRAVERSAL_PATHS cap


# ---------------------------------------------------------------------------
# check_outputs_excerpt_truncated
# ---------------------------------------------------------------------------


def test_check_outputs_excerpt_truncated_true_for_large_outputs() -> None:
    record = {"outputs_for_continuity": {"text": "x" * 5000}}
    assert check_outputs_excerpt_truncated(record, max_chars=2500)


def test_check_outputs_excerpt_truncated_false_for_small_outputs() -> None:
    record = {"outputs_for_continuity": {"text": "hello"}}
    assert not check_outputs_excerpt_truncated(record, max_chars=2500)


def test_check_outputs_excerpt_truncated_false_for_empty_record() -> None:
    assert not check_outputs_excerpt_truncated({}, max_chars=2500)


def test_check_outputs_excerpt_truncated_independent_of_result_truncated_flag() -> None:
    """result_truncated=False doesn't suppress the excerpt-truncation check."""
    large_record = {
        "result_truncated": False,
        "outputs_for_continuity": {"key": "y" * 3000},
    }
    assert check_outputs_excerpt_truncated(large_record, max_chars=2500)


# ---------------------------------------------------------------------------
# build_recent_tool_result_slices — structural_metadata field
# ---------------------------------------------------------------------------


def test_slices_include_outputs_structural_metadata_field() -> None:
    records = [_result_record(1, outputs={"status": "ok", "items": []})]
    slices = build_recent_tool_result_slices(records)
    assert len(slices) == 1
    assert "outputs_structural_metadata" in slices[0]
    assert "latest_artifact_ref" in slices[0]


def test_slices_structural_metadata_has_top_level_keys_for_mapping_outputs() -> None:
    records = [_result_record(1, outputs={"key_a": "val", "key_b": 42})]
    slices = build_recent_tool_result_slices(records)
    assert slices[0]["outputs_structural_metadata"] is None


def test_slices_structural_metadata_is_none_for_string_outputs() -> None:
    records = [_result_record(1, outputs="plain text")]
    slices = build_recent_tool_result_slices(records)
    assert slices[0]["outputs_structural_metadata"] is None


def test_slices_structural_metadata_visible_even_when_excerpt_truncated() -> None:
    """Key lists are extracted before truncation, so metadata is complete even when excerpt is cut."""
    big_outputs = {"top_key": "x" * 5000, "status": "ok"}
    records = [_result_record(1, outputs=big_outputs)]
    slices = build_recent_tool_result_slices(records, max_chars_per_result=100)
    assert slices[0]["outputs_excerpt_truncated"] is True
    meta = slices[0]["outputs_structural_metadata"]
    assert meta is not None
    assert "top_key" in meta["top_level_keys"]
    assert "status" in meta["top_level_keys"]


def test_slices_include_latest_artifact_ref_from_first_artifact_ref() -> None:
    record = _result_record(1, outputs={"status": "ok"})
    record["artifact_refs"] = ["artifact://latest", "artifact://aggregate"]
    slices = build_recent_tool_result_slices([record])
    assert slices[0]["latest_artifact_ref"] == "artifact://latest"


def test_slices_structural_metadata_present_when_raw_result_is_truncated() -> None:
    records = [
        _result_record(
            1,
            outputs={"status": "ok", "payload": {"key_a": "val", "key_b": 42}},
            result_truncated=True,
        )
    ]
    slices = build_recent_tool_result_slices(records)
    meta = slices[0]["outputs_structural_metadata"]
    assert meta is not None
    assert "top_level_keys" in meta
    assert "status" in meta["top_level_keys"]
    assert "payload" in meta["top_level_keys"]


def test_slices_structural_metadata_exposes_run6_payload_shape() -> None:
    """Slice metadata must expose results[0].payload.payload keys for run-6-shaped artifacts."""
    run6_outputs = {
        "results": [
            {
                "payload": {
                    "payload": {
                        "source_transcript_verbatim": {"text": "long text " * 500},
                        "parcel_metadata": {"parcel_count": 2},
                    }
                }
            }
        ]
    }
    records = [_result_record(1, outputs=run6_outputs)]
    slices = build_recent_tool_result_slices(records, max_chars_per_result=500)
    assert slices[0]["outputs_excerpt_truncated"] is True
    meta = slices[0]["outputs_structural_metadata"]
    assert meta is not None
    all_values = [v for v in meta.values() if isinstance(v, list)]
    assert any("source_transcript_verbatim" in v for v in all_values), (
        f"source_transcript_verbatim not found in slice metadata; meta={meta}"
    )


def test_slices_structural_metadata_includes_field_presence_signals_for_text_lanes() -> None:
    run6_outputs = {
        "results": [
            {
                "payload": {
                    "payload": {
                        "source_transcript_verbatim": {"text": "verbatim text " * 300},
                        "normalized_or_mapping_transcript": {"text": ""},
                        "issues": [],
                    }
                }
            }
        ]
    }
    records = [_result_record(1, outputs=run6_outputs)]
    slices = build_recent_tool_result_slices(records, max_chars_per_result=200)
    meta = slices[0]["outputs_structural_metadata"]
    assert meta is not None
    signals = meta.get("field_signals")
    assert isinstance(signals, dict)
    verbatim_path = "results[0].payload.payload.source_transcript_verbatim.text"
    normalized_path = "results[0].payload.payload.normalized_or_mapping_transcript.text"
    assert signals[verbatim_path]["non_empty"] is True
    assert signals[verbatim_path]["char_length"] > 100
    assert signals[normalized_path]["non_empty"] is False
