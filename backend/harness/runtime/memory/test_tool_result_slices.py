"""Tests for tool_result_slices.py — structural metadata and excerpt-boundary awareness."""
from __future__ import annotations

from harness.runtime.memory.continuity_journal import CLIP_SENTINEL_KEY
from harness.runtime.memory.tool_result_slices import (
    _extract_evidence_artifact_summary,
    _extract_structural_metadata,
    _extract_text_field_summaries,
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


# ---------------------------------------------------------------------------
# Track 4: Evidence artifact summary in tool result slices
# ---------------------------------------------------------------------------


def test_evidence_artifact_summary_none_for_empty_outputs() -> None:
    assert _extract_evidence_artifact_summary({}) is None


def test_evidence_artifact_summary_none_for_string_outputs() -> None:
    assert _extract_evidence_artifact_summary("plain text") is None


def test_evidence_artifact_summary_extracts_rendered_evidence_refs() -> None:
    """render_evidence_locators shape: outputs.rendered_evidence_refs is extracted."""
    outputs = {
        "rendered_evidence_refs": [
            {
                "source_ref": "image:assoc:tx:original",
                "rendered_ref": "image:derived:tx:locators_rendered",
                "locator_count": 3,
                "summary_only_locator_count": 0,
                "unsupported_locator_count": 0,
            }
        ]
    }
    summary = _extract_evidence_artifact_summary(outputs)
    assert summary is not None
    assert "rendered_evidence_refs" in summary
    row = summary["rendered_evidence_refs"][0]
    assert row["source_ref"] == "image:assoc:tx:original"
    assert row["rendered_ref"] == "image:derived:tx:locators_rendered"
    assert row["locator_count"] == 3


def test_evidence_artifact_summary_extracts_derived_ref() -> None:
    """transform_artifact shape: top-level derived_ref is extracted."""
    outputs = {
        "derived_ref": "image:derived:tx:crop_001",
        "source_ref": "image:assoc:tx:original",
    }
    summary = _extract_evidence_artifact_summary(outputs)
    assert summary is not None
    assert summary["derived_ref"] == "image:derived:tx:crop_001"
    assert summary["source_ref"] == "image:assoc:tx:original"


def test_evidence_artifact_summary_extracts_derived_refs_list() -> None:
    outputs = {
        "derived_refs": [
            "image:derived:tx:crop_001",
            "image:derived:tx:crop_002",
        ]
    }
    summary = _extract_evidence_artifact_summary(outputs)
    assert summary is not None
    assert summary["derived_refs"] == [
        "image:derived:tx:crop_001",
        "image:derived:tx:crop_002",
    ]


def test_evidence_artifact_summary_none_when_no_evidence_fields() -> None:
    outputs = {"status": "ok", "count": 3, "items": []}
    assert _extract_evidence_artifact_summary(outputs) is None


def test_slices_include_evidence_artifact_summary_for_rendered_result() -> None:
    """build_recent_tool_result_slices surfaces evidence_artifact_summary when present."""
    outputs = {
        "rendered_evidence_refs": [
            {
                "source_ref": "image:assoc:tx:original",
                "rendered_ref": "image:derived:tx:rendered",
                "locator_count": 2,
                "summary_only_locator_count": 0,
                "unsupported_locator_count": 1,
            }
        ]
    }
    records = [_result_record(1, outputs=outputs, action_type="render_evidence_locators")]
    slices = build_recent_tool_result_slices(records)
    assert len(slices) == 1
    assert "evidence_artifact_summary" in slices[0]
    eas = slices[0]["evidence_artifact_summary"]
    assert eas["rendered_evidence_refs"][0]["rendered_ref"] == "image:derived:tx:rendered"
    assert eas["rendered_evidence_refs"][0]["unsupported_locator_count"] == 1


def test_slices_include_evidence_artifact_summary_for_transform_result() -> None:
    """transform_artifact results expose derived_ref and source_ref in the slice."""
    outputs = {
        "derived_ref": "image:derived:tx:crop_001",
        "source_ref": "image:assoc:tx:original",
    }
    records = [_result_record(1, outputs=outputs, action_type="transform_artifact")]
    slices = build_recent_tool_result_slices(records)
    assert "evidence_artifact_summary" in slices[0]
    eas = slices[0]["evidence_artifact_summary"]
    assert eas["derived_ref"] == "image:derived:tx:crop_001"
    assert eas["source_ref"] == "image:assoc:tx:original"


def test_slices_no_evidence_artifact_summary_when_absent() -> None:
    """When no evidence fields are present, evidence_artifact_summary is omitted."""
    records = [_result_record(1, outputs={"status": "ok"})]
    slices = build_recent_tool_result_slices(records)
    assert "evidence_artifact_summary" not in slices[0]


def test_slices_evidence_artifact_summary_present_even_when_excerpt_not_truncated() -> None:
    """evidence_artifact_summary is always included when fields are present, not only on truncation."""
    outputs = {
        "derived_ref": "image:derived:tx:small_crop",
        "source_ref": "image:assoc:tx:original",
        "status": "ok",
    }
    records = [_result_record(1, outputs=outputs)]
    slices = build_recent_tool_result_slices(records, max_chars_per_result=5000)
    assert slices[0]["outputs_excerpt_truncated"] is False
    assert "evidence_artifact_summary" in slices[0]


def test_evidence_artifact_summary_extracts_real_transform_artifact_keys() -> None:
    """Real transform_artifact output uses derived_ref_id / parent_ref_id — must be normalised."""
    outputs = {
        "derived_ref_id": "image:derived:tx:crop_001",
        "parent_ref_id": "image:assoc:tx:original",
        "status": "ok",
    }
    summary = _extract_evidence_artifact_summary(outputs)
    assert summary is not None
    assert summary["derived_ref"] == "image:derived:tx:crop_001"
    assert summary["source_ref"] == "image:assoc:tx:original"


def test_slices_evidence_artifact_summary_for_real_transform_shape() -> None:
    """build_recent_tool_result_slices surfaces derived_ref/source_ref from real transform output."""
    outputs = {
        "derived_ref_id": "image:derived:tx:zoom_002",
        "parent_ref_id": "image:assoc:tx:page1",
        "width": 800,
        "height": 600,
    }
    records = [_result_record(1, outputs=outputs, action_type="transform_artifact")]
    slices = build_recent_tool_result_slices(records)
    assert "evidence_artifact_summary" in slices[0]
    eas = slices[0]["evidence_artifact_summary"]
    assert eas["derived_ref"] == "image:derived:tx:zoom_002"
    assert eas["source_ref"] == "image:assoc:tx:page1"


# ---------------------------------------------------------------------------
# Track 1: text_field_summaries
# ---------------------------------------------------------------------------


def test_text_field_summaries_includes_field_above_old_cap_as_complete() -> None:
    """A text field > old 2500 char cap but within full cap must appear is_complete=True."""
    text_value = "a" * 3500  # > old 2500 cap, < 12000 full cap
    records = [_result_record(1, outputs={"body": text_value})]
    slices = build_recent_tool_result_slices(records, max_chars_per_result=2500)
    # Old generic excerpt was truncated
    assert slices[0]["outputs_excerpt_truncated"] is True
    summaries = slices[0].get("text_field_summaries")
    assert summaries is not None, "text_field_summaries must be present when text fields exist"
    assert len(summaries) == 1
    entry = summaries[0]
    assert entry["path"] == "body"
    assert entry["char_length"] == 3500
    assert entry["is_complete"] is True
    assert entry["text"] == text_value


def test_text_field_summaries_marks_large_field_incomplete_with_excerpt_range() -> None:
    """A text field exceeding the full cap must appear as is_complete=False with range markers."""
    text_value = "z" * 15000  # > 12000 full cap
    records = [_result_record(1, outputs={"content": text_value})]
    slices = build_recent_tool_result_slices(records)
    summaries = slices[0].get("text_field_summaries")
    assert summaries is not None
    entry = summaries[0]
    assert entry["path"] == "content"
    assert entry["char_length"] == 15000
    assert entry["is_complete"] is False
    assert entry["excerpt_start"] == 0
    assert entry["excerpt_end"] <= 12000
    assert len(entry["excerpt"]) == entry["excerpt_end"]
    assert entry.get("truncation_reason") == "prompt_projection_cap"


def test_text_field_summaries_not_hidden_by_metadata_heavy_output() -> None:
    """Text fields appear in text_field_summaries even when metadata keys fill the JSON excerpt."""
    long_text = "t" * 3000
    outputs = {
        "status": "ok",
        "version": "1.0",
        "run_id": "abc123",
        "phase": "main",
        "result_code": "success",
        "iteration": 5,
        "text_body": long_text,  # appears last — JSON excerpt would be full of metadata before this
    }
    records = [_result_record(1, outputs=outputs)]
    slices = build_recent_tool_result_slices(records, max_chars_per_result=200)
    assert slices[0]["outputs_excerpt_truncated"] is True
    summaries = slices[0].get("text_field_summaries")
    assert summaries is not None
    paths = [e["path"] for e in summaries]
    assert "text_body" in paths, f"text_body not found in text_field_summaries paths: {paths}"
    text_entry = next(e for e in summaries if e["path"] == "text_body")
    assert text_entry["is_complete"] is True
    assert text_entry["text"] == long_text


def test_text_field_summaries_none_when_no_meaningful_text_fields() -> None:
    """text_field_summaries is absent when all string values are below the min length."""
    outputs = {"status": "ok", "count": 3, "kind": "hydrate"}
    records = [_result_record(1, outputs=outputs)]
    slices = build_recent_tool_result_slices(records)
    assert "text_field_summaries" not in slices[0]


def test_text_field_summaries_traverses_nested_mapping() -> None:
    """Text fields nested inside a mapping appear with their full dotted path."""
    nested_text = "n" * 200
    outputs = {"payload": {"source_text": nested_text}}
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    assert len(summaries) == 1
    assert summaries[0]["path"] == "payload.source_text"
    assert summaries[0]["is_complete"] is True
    assert summaries[0]["text"] == nested_text


def test_text_field_summaries_traverses_multiple_list_elements() -> None:
    """All list elements (not just index 0) must contribute text fields to text_field_summaries."""
    def _item(i: int) -> dict:
        return {"ref": f"artifact://rev:{i:04d}", "text": f"body text for item {i} " * 20}

    outputs = {"results": [_item(i) for i in range(3)]}
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    paths = [e["path"] for e in summaries]
    assert "results[0].text" in paths, f"results[0].text missing from {paths}"
    assert "results[1].text" in paths, f"results[1].text missing from {paths}"
    assert "results[2].text" in paths, f"results[2].text missing from {paths}"


def test_newest_result_not_crowded_out_by_large_older_text_result() -> None:
    """A large text_field_summaries on an older result must not prevent the newest result appearing."""
    old_record = _result_record(1, outputs={"body": "x" * 30000})  # huge — fills any budget
    new_record = _result_record(2, outputs={"status": "done", "count": 1})
    slices = build_recent_tool_result_slices(
        [old_record, new_record],
        max_records=3,
        max_total_chars=7000,
    )
    turns = [s["kernel_turn_index"] for s in slices]
    assert 2 in turns, f"Newest turn 2 was crowded out by older large result; turns present: {turns}"
    # Output is in chronological order
    assert turns == sorted(turns), f"Slices are not in chronological order: {turns}"


def test_slices_chronological_order_preserved_after_newest_first_iteration() -> None:
    """When multiple rows fit the budget they must be returned oldest-to-newest."""
    records = [_result_record(t, outputs={"k": str(t)}) for t in (1, 2, 3)]
    slices = build_recent_tool_result_slices(records, max_records=3)
    turns = [s["kernel_turn_index"] for s in slices]
    assert turns == sorted(turns)


def test_text_field_summaries_peer_hydrate_shape_exposes_all_drafts() -> None:
    """Simulate a peer-draft hydrate result: each results[N].payload.text must be visible."""
    def _draft(i: int) -> dict:
        return {
            "ref_id": f"t0:raw:draft_{i}",
            "kind": "t0_draft",
            "payload": {"text": f"draft content {i} " * 50},
        }

    outputs = {"results": [_draft(i) for i in range(3)]}
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    paths = [e["path"] for e in summaries]
    assert "results[0].payload.text" in paths, f"results[0].payload.text missing; paths={paths}"
    assert "results[1].payload.text" in paths, f"results[1].payload.text missing; paths={paths}"
    assert "results[2].payload.text" in paths, f"results[2].payload.text missing; paths={paths}"


def test_field_signal_includes_is_complete_for_string_fields() -> None:
    """_extract_structural_metadata field_signals must include is_complete on string entries."""
    outputs = {
        "medium_text": "m" * 3000,   # < 12000 full cap → is_complete True
        "large_text": "l" * 15000,   # > 12000 full cap → is_complete False
    }
    meta = _extract_structural_metadata(outputs)
    assert meta is not None
    signals = meta.get("field_signals", {})
    assert "medium_text" in signals
    assert signals["medium_text"]["is_complete"] is True
    assert "large_text" in signals
    assert signals["large_text"]["is_complete"] is False


# ---------------------------------------------------------------------------
# Run-16 regression: 3-draft hydrate outputs preserved after continuity cap raise
# ---------------------------------------------------------------------------

_RUN16_DRAFT_TEXT = (
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
    "less as surveyed by licensed surveyor John Doe on January 15, 2024. "
) * 4  # ~2960 chars — mirrors real run-16 per-draft size


def _run16_outputs() -> dict:
    """3-draft hydrate shape matching run-16 turn-1 outputs after the cap is raised."""
    return {
        "t0:raw:draft_1": {"text": _RUN16_DRAFT_TEXT, "source": "llm", "model": "gpt-4o-mini"},
        "t0:raw:draft_2": {"text": _RUN16_DRAFT_TEXT, "source": "llm", "model": "gpt-4o-mini"},
        "t0:raw:draft_3": {"text": _RUN16_DRAFT_TEXT, "source": "llm", "model": "gpt-4o-mini"},
    }


def test_run16_text_field_summaries_all_three_drafts_complete() -> None:
    """Regression: after the continuity cap raise, all 3 draft texts must appear as is_complete
    in text_field_summaries — not hidden by a string-prefix truncation.

    In run-16 the stored outputs were converted to a raw string prefix at 8192 chars,
    which caused _extract_text_field_summaries to receive a str (not a Mapping) and
    return None — leaving no text_field_summaries in the prompt slice at all.
    """
    outputs = _run16_outputs()
    # Verify the fixture is a proper Mapping (not a string) — simulating the post-fix world
    assert isinstance(outputs, dict), "Fixture must be a dict (simulating post-cap-raise storage)"

    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None, (
        "text_field_summaries must not be None when outputs is a full dict with text fields"
    )
    paths = {s["path"] for s in summaries}
    assert "t0:raw:draft_1.text" in paths, f"draft_1 text must appear in summaries; paths={paths}"
    assert "t0:raw:draft_2.text" in paths, f"draft_2 text must appear in summaries; paths={paths}"
    assert "t0:raw:draft_3.text" in paths, f"draft_3 text must appear in summaries; paths={paths}"


def test_run16_text_field_summaries_drafts_are_complete() -> None:
    """Each draft text (~2960 chars) is below the 12000-char full cap so is_complete must be True."""
    outputs = _run16_outputs()
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    for entry in summaries:
        if entry["path"].endswith(".text"):
            assert entry.get("is_complete") is True, (
                f"Draft text at {entry['path']} should be is_complete=True "
                f"(char_length={entry.get('char_length')})"
            )


def test_run16_slice_contains_text_field_summaries() -> None:
    """build_recent_tool_result_slices must include text_field_summaries for run-16 outputs."""
    records = [
        _result_record(1, outputs=_run16_outputs(), result_truncated=False),
    ]
    slices = build_recent_tool_result_slices(records)
    assert slices, "Must produce at least one slice"
    s = slices[0]
    assert "text_field_summaries" in s, (
        "Slice must have text_field_summaries when outputs contain dict with text fields"
    )
    paths = {e["path"] for e in s["text_field_summaries"]}
    assert "t0:raw:draft_1.text" in paths
    assert "t0:raw:draft_2.text" in paths
    assert "t0:raw:draft_3.text" in paths


def test_run16_string_prefix_outputs_yield_no_text_field_summaries() -> None:
    """Sanity check: if outputs_for_continuity is a string prefix (old broken behavior),
    text_field_summaries must be absent — proving the dict path is what drives summaries.
    """
    import json
    raw = json.dumps(_run16_outputs(), ensure_ascii=False, default=str, sort_keys=True)
    string_prefix = raw[:8192]  # old broken behavior
    assert isinstance(string_prefix, str)
    summaries = _extract_text_field_summaries(string_prefix)
    assert summaries is None, (
        "String input must yield no text_field_summaries — confirming why the old code failed"
    )


# ---------------------------------------------------------------------------
# Clip sentinel detection in _extract_text_field_summaries
# ---------------------------------------------------------------------------

def _make_sentinel(original_text: str, *, max_chars: int = 200) -> dict:
    """Build a clip sentinel dict as _clip_large_text_fields would produce."""
    return {
        CLIP_SENTINEL_KEY: True,
        "original_char_length": len(original_text),
        "excerpt": original_text[:max_chars],
    }


def test_text_field_summaries_recognizes_clip_sentinel_as_incomplete() -> None:
    """A clip sentinel at a text field path must appear as is_complete=False.

    Before this fix, _clip_large_text_fields returned a trimmed string that was
    shorter than _TEXT_FIELD_FULL_CAP, so is_complete was reported as True for
    what was actually partial text.
    """
    long_text = "x" * 5000
    outputs = {
        "t0:raw:draft_1": {
            "text": _make_sentinel(long_text, max_chars=200),
            "source": "llm",
        }
    }
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    text_entries = [s for s in summaries if s["path"] == "t0:raw:draft_1.text"]
    assert text_entries, f"Expected t0:raw:draft_1.text in summaries; got paths={[s['path'] for s in summaries]}"
    entry = text_entries[0]
    assert entry["is_complete"] is False, (
        "Clip sentinel must report is_complete=False regardless of excerpt length"
    )


def test_text_field_summaries_clip_sentinel_has_correct_original_char_length() -> None:
    """char_length in the summary must reflect the original field size, not the excerpt size."""
    long_text = "z" * 8000
    outputs = {
        "field": _make_sentinel(long_text, max_chars=300),
    }
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    field_entries = [s for s in summaries if s["path"] == "field"]
    assert field_entries, "Sentinel at root key must produce a summary at that path"
    entry = field_entries[0]
    assert entry["char_length"] == 8000, (
        f"char_length must be original_char_length (8000); got {entry['char_length']}"
    )
    assert entry["truncation_reason"] == "continuity_storage_clip"


def test_text_field_summaries_clip_sentinel_path_is_not_sentinel_subkey() -> None:
    """The sentinel must not recurse and emit paths like 'field.__clipped__' or 'field.excerpt'."""
    long_text = "y" * 4000
    outputs = {"data": _make_sentinel(long_text, max_chars=100)}
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    paths = {s["path"] for s in summaries}
    # Correct: path is at the sentinel node level
    assert "data" in paths, f"Expected 'data' in paths; got {paths}"
    # Must not recurse into the sentinel internals
    assert f"data.{CLIP_SENTINEL_KEY}" not in paths, "Must not emit path for __clipped__ key"
    assert "data.excerpt" not in paths, "Must not emit path for excerpt key as a separate field"
    assert "data.original_char_length" not in paths


def test_text_field_summaries_clip_sentinel_excerpt_is_bounded() -> None:
    """The excerpt in the summary must be bounded by _TEXT_FIELD_FULL_CAP."""
    # Make an excerpt that is itself 15000 chars (larger than _TEXT_FIELD_FULL_CAP=12000)
    long_text = "q" * 20000
    outputs = {
        "big_field": {
            CLIP_SENTINEL_KEY: True,
            "original_char_length": 20000,
            "excerpt": long_text[:15000],  # 15000-char excerpt
        }
    }
    summaries = _extract_text_field_summaries(outputs)
    assert summaries is not None
    entries = [s for s in summaries if s["path"] == "big_field"]
    assert entries
    entry = entries[0]
    assert entry["is_complete"] is False
    assert entry["char_length"] == 20000
    # The excerpt in the summary must be capped at _TEXT_FIELD_FULL_CAP (12000)
    assert len(entry.get("excerpt", "")) <= 12000, (
        "Sentinel excerpt must be capped at _TEXT_FIELD_FULL_CAP when the stored excerpt is large"
    )


def test_text_field_summaries_clip_sentinel_short_excerpt_skipped_when_below_min_length() -> None:
    """A sentinel whose original_char_length is below _TEXT_FIELD_MIN_LENGTH must be skipped."""
    short_text = "x" * 30  # below _TEXT_FIELD_MIN_LENGTH=60
    outputs = {
        "tiny": {
            CLIP_SENTINEL_KEY: True,
            "original_char_length": 30,
            "excerpt": short_text,
        }
    }
    summaries = _extract_text_field_summaries(outputs)
    # Should be None or not contain "tiny"
    if summaries is not None:
        paths = {s["path"] for s in summaries}
        assert "tiny" not in paths, "Short clip sentinel must be skipped like short plain strings"
