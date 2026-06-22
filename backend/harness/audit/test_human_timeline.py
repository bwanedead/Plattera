from __future__ import annotations

from pathlib import Path

from harness.audit.human_timeline import render_timeline
from harness.audit.run_audit_writer import RunAuditWriter


TIMELINE_REL = ("audit", "human", "timeline.md")


def _timeline_path(run_dir: Path) -> Path:
    return run_dir.joinpath(*TIMELINE_REL)


def test_timeline_renders_parent_llm_call_trace(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-llm-trace")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "llm_call_trace": {
                "provider": "openai",
                "call_role": "parent",
                "call_name": "choose_action",
                "model": "gpt-5.4",
                "started_at_epoch_seconds": 100.0,
                "finished_at_epoch_seconds": 157.4,
                "wall_seconds": 57.4,
                "prompt_char_count": 187161,
                "response_char_count": 4200,
                "input_tokens": 40086,
                "cached_input_tokens": 1200,
                "output_tokens": 900,
                "reasoning_tokens": 300,
                "total_tokens": 40986,
                "service_tier_requested": None,
                "service_tier_returned": "default",
                "streaming_requested": False,
                "streaming_supported": True,
            },
        }
    )
    body = _timeline_path(tmp_path / "run-llm-trace").read_text(encoding="utf-8")
    assert "LLM call:" in body
    assert "provider/model: openai / gpt-5.4" in body
    assert "wall: 57.4s" in body
    assert "prompt=187161" in body
    assert "input=40086" in body
    assert "cached=1200" in body
    assert "streaming: requested=false supported=true" in body
    assert "first_event:" not in body
    assert "provider_wait:" not in body


def test_timeline_renders_streaming_first_event_timing(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-llm-stream")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "llm_call_trace": {
                "provider": "openai",
                "call_role": "parent",
                "call_name": "choose_action",
                "model": "gpt-5.4",
                "started_at_epoch_seconds": 100.0,
                "finished_at_epoch_seconds": 110.0,
                "wall_seconds": 10.0,
                "prompt_char_count": 1000,
                "response_char_count": 200,
                "streaming_requested": True,
                "streaming_supported": True,
                "first_response_event_at_epoch_seconds": 104.0,
                "time_to_first_response_event_seconds": 4.0,
                "provider_wait_seconds": 4.0,
                "response_stream_seconds": 6.0,
            },
        }
    )
    body = _timeline_path(tmp_path / "run-llm-stream").read_text(encoding="utf-8")
    assert "first_event: 4.0s" in body
    assert "provider_wait: 4.0s" in body
    assert "response_stream: 6.0s" in body


def test_timeline_renders_host_hydration_and_output_gate(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-hydration-gate")
    writer.observe_llm_io(
        {
            "turn_index": 4,
            "parse_ok": True,
            "host_hydration_before_turn": {
                "agent_requested_hydration": {
                    "requested_refs": ["transcript_edit:working:rev:0002"],
                    "resolved_refs": ["transcript_edit:working:rev:0002"],
                    "status": "surfaced",
                    "source_turn_index": 3,
                    "hydrated_result_count": 1,
                },
                "pinned_refs_auto_hydration": {
                    "refs": ["transcript_edit:working:rev:0002"],
                    "status": "surfaced",
                    "hydrated_result_count": 1,
                },
            },
            "tool_request": {
                "actions": [
                    {
                        "alias": "save",
                        "action_type": "save_workspace_artifact",
                        "action_inputs": {"transcript_text": "line 1"},
                        "hydrate_next": ["@result.revision_ref"],
                    }
                ],
                "rationale": "save working copy",
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 4,
            "required_output_gate": {
                "reason_code": "missing_required_output_artifact:transcript_edit:output",
                "strike_count": 2,
                "max_strikes": 3,
                "outcome": "repairable_continue",
            },
            "recent_action_sequence_result": {
                "sequence_id": "seq-4",
                "items": [
                    {
                        "alias": "save",
                        "action_type": "save_workspace_artifact",
                        "execution_state": "executed",
                    }
                ],
            },
        }
    )
    body = _timeline_path(tmp_path / "run-hydration-gate").read_text(encoding="utf-8")
    assert "Host Hydration (before choose_action)" in body
    assert "agent_requested_hydration" in body
    assert "pinned_refs_auto_hydration" in body
    assert "Required Output Gate" in body
    assert "missing_required_output_artifact:transcript_edit:output" in body
    assert "Action Sequence Results" in body
    assert "save: save_workspace_artifact | executed" in body
    assert "b64" not in body.lower()


def test_timeline_renders_expiring_pinned_refs(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-pins-expiring")
    writer.observe_llm_io(
        {
            "turn_index": 8,
            "parse_ok": True,
            "tool_request": {
                "actions": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 8,
            "pinned_refs": {
                "active": [
                    {
                        "ref": "image:derived:crop-a",
                        "expires_in_turns": 1,
                        "last_refreshed_turn": 7,
                        "ttl_turns": 8,
                    }
                ],
                "expiring_soon": [
                    {
                        "ref": "image:derived:crop-a",
                        "expires_in_turns": 1,
                        "last_refreshed_turn": 7,
                        "ttl_turns": 8,
                    }
                ],
            },
        }
    )
    body = _timeline_path(tmp_path / "run-pins-expiring").read_text(encoding="utf-8")
    assert "expiring_soon:" in body
    assert "image:derived:crop-a expires_in_turns=1" in body


def test_timeline_renders_pinned_refs_section(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-pins")
    writer.observe_llm_io(
        {
            "turn_index": 3,
            "parse_ok": True,
            "tool_request": {
                "actions": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
                "pin_refs": ["transcript_edit:working:rev:0002"],
                "unpin_refs": ["transcript_edit:working:rev:0001"],
                "rationale": "keep latest working revision visible",
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 3,
            "pin_refs_this_turn": ["transcript_edit:working:rev:0002"],
            "unpin_refs_this_turn": ["transcript_edit:working:rev:0001"],
            "pinned_refs": {
                "active": [{"ref": "transcript_edit:working:rev:0002", "pinned_at_turn": 3}],
            },
        }
    )
    body = _timeline_path(tmp_path / "run-pins").read_text(encoding="utf-8")
    assert "Pinned Refs" in body
    assert "pinned_this_turn" in body
    assert "transcript_edit:working:rev:0002" in body
    assert "active:" in body


def test_timeline_renders_stable_context_section(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run-stable-context")
    writer.observe_llm_io(
        {
            "turn_index": 4,
            "parse_ok": True,
            "tool_request": {
                "actions": [{"alias": "a", "action_type": "noop", "action_inputs": {}}],
                "state_patch": {
                    "stable_context": {
                        "upsert": [
                            {
                                "context_id": "parcel_1_t0_shape",
                                "body": "Compact agent-authored context note.",
                                "basis_refs": ["t0:raw:draft_1"],
                                "attached_entity_ids": ["p1_call1_distance"],
                            }
                        ]
                    }
                },
                "rationale": "persist orientation memory",
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 4,
            "state_patch_feedback": {
                "outcome": "applied",
                "detail": {
                    "stable_context": {
                        "upserted": ["parcel_1_t0_shape"],
                        "retired": [],
                        "skipped_rows": [],
                    }
                },
            },
            "stable_context": {
                "active": [
                    {
                        "context_id": "parcel_1_t0_shape",
                        "title": "Parcel 1 T0 shape",
                        "role": "orientation_memory",
                        "basis_refs": ["t0:raw:draft_1"],
                        "attached_entity_ids": ["p1_call1_distance"],
                        "body_excerpt": "Compact agent-authored context note.",
                        "expires_in_turns": 12,
                    }
                ]
            },
        }
    )
    body = _timeline_path(tmp_path / "run-stable-context").read_text(encoding="utf-8")
    assert "Stable Context" in body
    assert "upserted_this_turn:" in body
    assert "parcel_1_t0_shape" in body
    assert "active_index:" in body
    assert "basis_refs:" in body
    assert "attached_entity_ids:" in body
    assert "p1_call1_distance" in body
    assert "body_excerpt:" in body


def test_timeline_created_under_audit_human_after_llm_io(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "raw_prompt_text": "prompt",
            "tool_request": {
                "action_type": "noop",
                "action_inputs": {},
                "rationale": "quick sanity check before closure",
            },
        }
    )
    path = _timeline_path(tmp_path / "run1")
    assert path.exists()
    body = path.read_text(encoding="utf-8")
    assert "TURN 0001" in body
    assert "noop" in body
    assert "quick sanity check before closure" in body


def test_timeline_updates_after_turn_completed(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 2,
            "parse_ok": True,
            "tool_request": {
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["transcript_edit:working:rev:0001"]},
                "rationale": "compare saved draft to verified call sequence",
            },
        }
    )
    path = _timeline_path(tmp_path / "run1")
    first = path.read_text(encoding="utf-8")
    assert "execution_state" not in first  # no tool result yet

    writer.observe_turn_completed(
        {
            "turn_index": 2,
            "tool_request": {
                "action_type": "hydrate_artifact_refs",
                "action_inputs": {"ref_ids": ["transcript_edit:working:rev:0001"]},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"hydrated_count": 1, "note": "ok"},
                "artifact_refs": ["artifact://draft"],
                "refusal": None,
            },
            "mission_state_after": {
                "active_mode": "audit_sweep",
                "closure_state": {"overall_status": "in_review"},
            },
            "resolution_state_after": {
                "active_item_id": "parcel1-call-sequence-audit",
                "items": [
                    {
                        "item_id": "parcel1-call-sequence-audit",
                        "status": "in_progress",
                        "summary": "Audit the call sequence against verified source.",
                    }
                ],
            },
            "latest_refs_after": {"transcript_edit:working": "transcript_edit:working:rev:0001"},
            "state_patch_feedback": {"outcome": "no_patch"},
            "terminal_decision": None,
        }
    )
    second = path.read_text(encoding="utf-8")
    assert "execution_state: executed" in second
    assert "artifact://draft" in second
    assert "audit_sweep" in second
    assert "parcel1-call-sequence-audit" in second


def test_timeline_renders_operator_progress_near_top_and_none_when_absent(
    tmp_path: Path,
) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 2,
            "parse_ok": True,
            "tool_request": {
                "actions": [{"alias": "crop_a", "action_type": "transform_artifact", "action_inputs": {}}],
                "rationale": "INTERNAL_RATIONALE_TEXT",
                "operator_progress_message": "USER_FACING_PROGRESS_LINE",
            },
            "parsed_action_plan": {
                "actions": [{"alias": "crop_a", "action_type": "transform_artifact", "action_inputs": {}}],
                "rationale": "INTERNAL_RATIONALE_TEXT",
                "operator_progress_message": "USER_FACING_PROGRESS_LINE",
            },
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    progress_idx = body.index("Operator Progress")
    rationale_idx = body.index("  rationale:")
    assert progress_idx < rationale_idx
    assert "USER_FACING_PROGRESS_LINE" in body
    assert "actions:1 (crop_a:transform_artifact)" in body
    assert "  action_type: none" not in body

    writer.observe_llm_io(
        {
            "turn_index": 3,
            "parse_ok": True,
            "tool_request": {
                "state_patch": {"resolution": {"active_item_id": "item-1"}},
                "rationale": "state only",
            },
            "parsed_action_plan": {
                "state_patch": {"resolution": {"active_item_id": "item-1"}},
                "rationale": "state only",
            },
        }
    )
    body2 = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "operator_progress_message: none" in body2


def test_timeline_renders_native_action_details_and_hydrate_next(
    tmp_path: Path,
) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 4,
            "parse_ok": True,
            "tool_request": {
                "actions": [
                    {
                        "alias": "crop_opening",
                        "action_type": "transform_artifact",
                        "action_inputs": {
                            "ref_id": "image:source:1",
                            "sub_action": "crop",
                            "box": [10, 20, 110, 80],
                        },
                        "hydrate_next": ["@this.result.derived_ref_id"],
                        "hydrate_next_reason": "Inspect the crop before determining the value.",
                    },
                    {
                        "alias": "crop_calls",
                        "action_type": "transform_artifact",
                        "action_inputs": {
                            "ref_id": "image:source:1",
                            "sub_action": "crop",
                            "box": [100, 200, 400, 300],
                        },
                    },
                ],
                "rationale": "Create two crops in one turn.",
                "operator_progress_message": "Creating two localized crops to inspect next.",
            },
            "parsed_action_plan": {},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "actions:2 (transform_artifact, transform_artifact)" in body
    assert "    - crop_opening: transform_artifact" in body
    assert "      hydrate_next:" in body
    assert "        - @this.result.derived_ref_id" in body
    assert "      hydrate_next_reason:" in body
    assert "Inspect the crop before determining the value." in body
    assert "      action_inputs:" in body
    assert '"sub_action": "crop"' in body
    assert "    - crop_calls: transform_artifact" in body
    assert "      hydrate_next: none" in body


def test_timeline_shows_all_llm_authored_prose_fields(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "tool_request": {
                "action_type": "noop",
                "action_inputs": {},
                "rationale": "RATIONALE_PROSE",
            },
            "parsed_action_plan": {
                "action_type": "noop",
                "rationale": "RATIONALE_PROSE",
                "operator_progress_message": "OPERATOR_STATUS_LINE",
                "continuity_journal_entry": {"new_insight": "CONT_JOURNAL_TEXT"},
                "hitl_request": {
                    "message": "HITL_PROMPT_MESSAGE",
                    "choices": ["Option A", "Option B"],
                    "context": {"notes": "HITL_CONTEXT_NOTES"},
                },
            },
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "Operator Progress" in body
    assert body.index("Operator Progress") < body.index("LLM Authored Text")
    assert "RATIONALE_PROSE" in body
    assert "OPERATOR_STATUS_LINE" in body
    assert "CONT_JOURNAL_TEXT" in body
    assert "HITL_PROMPT_MESSAGE" in body
    assert "Option A" in body
    assert "HITL_CONTEXT_NOTES" in body


def test_timeline_shows_parse_error_detail_and_action_counts(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 2,
            "parse_ok": False,
            "parse_reason_code": "invalid_model_action_json",
            "parse_error_detail": (
                "invalid_model_action_json: actions failed canonical validation: "
                "action_batch exceeds per-tool cap for transform_artifact (4)"
            ),
            "original_action_count_attempted": 5,
            "native_actions_attempted": True,
            "repair_attempted": True,
            "repair_records": [
                {
                    "repair_parse_ok": True,
                    "repaired_action_count": 4,
                    "repair_parsed_action_plan": {
                        "actions": [{"alias": f"c{i}", "action_type": "transform_artifact"} for i in range(4)],
                    },
                }
            ],
        }
    )
    writer.finalize(
        terminal_class="failed",
        reason_code="invalid_model_action_json",
        iterations=2,
        latest_refs={},
        trace_events=[],
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "action_parse_failure" in body
    assert "parse_error_detail:" in body
    assert "exceeds per-tool" in body
    assert "transform_artifact (4)" in body
    assert "original_action_count_attempted: 5" in body
    assert "native_actions_attempted: True" in body
    assert "repaired_action_count: 4" in body
    assert "repair_action_count: reduced_to_cap_or_valid_rows" in body
    assert "b64" not in body.lower()


def test_timeline_shows_raw_response_excerpt_when_parse_failed(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": False,
            "parse_reason_code": "invalid_model_action_json",
            "raw_llm_response_text": "RAW_UNPARSEABLE_MODEL_OUTPUT",
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "raw_llm_response_excerpt" in body
    assert "RAW_UNPARSEABLE_MODEL_OUTPUT" in body


def test_timeline_shows_model_failure_provider_metadata(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 18,
            "prompt_mode": "resume",
            "parse_ok": False,
            "parse_reason_code": "model_call_failed",
            "provider_finish_reason": "length",
            "provider_error": "OpenAI returned truncated response (finish_reason: length)",
            "provider_prompt_tokens": 25966,
            "provider_completion_tokens": 16000,
            "raw_llm_response_char_count": 0,
        }
    )

    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "action_parse_failure" in body
    assert "parse_reason_code: model_call_failed" in body
    assert "provider_finish_reason: length" in body
    assert "provider_completion_tokens: 16000" in body
    assert "OpenAI returned truncated response" in body


def test_timeline_displays_tool_request_and_result(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {
                "action_type": "my_tool",
                "action_inputs": {"ref_ids": ["a", "b"]},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"note": "DONE_OUTPUT"},
                "artifact_refs": ["artifact://x"],
                "refusal": None,
            },
            "latest_refs_after": {"x": "artifact://x"},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "my_tool" in body
    assert "DONE_OUTPUT" in body
    assert "artifact://x" in body
    assert "outcome: applied" in body


def test_timeline_displays_mission_and_resolution_snapshots(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": None,
            "tool_result_raw": None,
            "mission_state_after": {
                "active_mode": "investigating",
                "success_conditions": [
                    {"condition_id": "sc-1", "status": "open", "blocking": True},
                ],
                "closure_state": {
                    "overall_status": "open",
                    "ready_to_close": False,
                    "ready_to_publish": False,
                    "dimensions": [
                        {"dimension_id": "dim-1", "status": "open", "blocking": True}
                    ],
                },
            },
            "resolution_state_after": {
                "active_item_id": "item-1",
                "items": [
                    {
                        "item_id": "item-1",
                        "status": "in_progress",
                        "structure_kind": "atomic",
                        "blocking": False,
                        "requires_hitl": False,
                        "summary": "ITEM_SUMMARY_TEXT",
                        "next_needed_step": "ITEM_NEXT_STEP",
                    },
                    {
                        "item_id": "item-2",
                        "status": "blocked",
                        "requires_hitl": True,
                        "verification_basis": "ITEM2_BASIS",
                    },
                ],
                "relations": [
                    {
                        "source_item_id": "item-1",
                        "target_item_id": "item-2",
                        "relation_type": "blocks",
                    }
                ],
            },
            "latest_refs_after": {},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "active_mode: investigating" in body
    assert "motion_posture: inventory" in body
    assert "sc-1" in body
    assert "item-1" in body
    assert "ITEM_SUMMARY_TEXT" in body
    assert "ITEM_NEXT_STEP" in body
    assert "item-2" in body
    assert "ITEM2_BASIS" in body
    assert "dim-1" in body
    assert "ready_to_close: false" in body
    assert "blocks" in body


def test_timeline_truncates_long_prose_and_marks_it(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    huge = "x" * 20000
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "tool_request": {
                "action_type": "noop",
                "action_inputs": {},
                "rationale": huge,
            },
            "parsed_action_plan": {
                "action_type": "noop",
                "rationale": huge,
            },
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "[truncated to" in body
    assert huge not in body


def test_timeline_bounds_tool_outputs_and_strips_binary(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    huge_output = {"note": "visible_text", "image_bytes": "AAAAAA" * 5000}
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {"action_type": "read_page"},
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": huge_output,
                "artifact_refs": [],
                "refusal": None,
                "image_evidence": [{"ref_id": "img:1", "data": "ZZZZ" * 500}],
            },
            "latest_refs_after": {},
            "state_patch_feedback": {},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "visible_text" in body
    assert "image_bytes" not in body
    assert "AAAAAA" not in body
    assert "image_evidence_count: 1" in body
    assert "ZZZZ" not in body


def test_timeline_projects_evidence_locator_and_rendered_evidence_summaries(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {
                "action_type": "transform_artifact",
                "action_inputs": {"sub_action": "render_evidence_locators"},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {
                    "rendered_evidence_refs": [
                        {
                            "source_ref": "artifact://source",
                            "rendered_ref": "artifact://source.annotated",
                            "locator_count": 1,
                            "summary_only_locator_count": 0,
                            "unsupported_locator_count": 0,
                        }
                    ]
                },
                "artifact_refs": ["artifact://source.annotated"],
                "refusal": None,
            },
            "resolution_state_after": {
                "items": [
                    {
                        "item_id": "item-a",
                        "title": "Item A",
                        "kind": "check",
                        "status": "closed",
                        "covered_units": [
                            {
                                "unit_id": "unit-a",
                                "title": "Unit A",
                                "status": "closed",
                                "determination": "earned",
                                "evidence_refs": ["artifact://source"],
                                "evidence_locators": [
                                    {
                                        "ref_id": "artifact://source",
                                        "locator_kind": "image_region",
                                        "label": "Value A",
                                        "box_norm": [0.1, 0.2, 0.3, 0.4],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            },
            "latest_refs_after": {},
            "state_patch_feedback": {},
        }
    )

    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "rendered_evidence_refs:" in body
    assert "source_ref: artifact://source | rendered_ref: artifact://source.annotated" in body
    assert "summary_only:0 | unsupported:0" in body
    assert "evidence_locators:" in body
    assert "kind:image_region | ref:artifact://source | label:Value A" in body
    assert "box_norm:[0.1, 0.2, 0.3, 0.4]" in body


def test_timeline_preserves_textual_outputs_data_but_not_image_evidence(tmp_path: Path) -> None:
    """Generic outputs.data must be preserved as visible payload; image_evidence payloads
    must not leak (image_evidence is counted, not dumped)."""
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {"action_type": "fetch_json"},
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"data": "TEXTUAL_DATA_PAYLOAD_VISIBLE"},
                "artifact_refs": [],
                "refusal": None,
                "image_evidence": [
                    {"ref_id": "img:1", "data": "IMAGE_BYTES_MUST_NOT_APPEAR" * 20}
                ],
            },
            "latest_refs_after": {},
            "state_patch_feedback": {},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "TEXTUAL_DATA_PAYLOAD_VISIBLE" in body
    assert "IMAGE_BYTES_MUST_NOT_APPEAR" not in body
    assert "image_evidence_count: 1" in body


def test_timeline_does_not_author_semantic_verdicts(tmp_path: Path) -> None:
    """Writer must not invent host-authored conclusions like 'stuck' or 'spinning'."""
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "tool_request": {
                "action_type": "noop",
                "action_inputs": {},
                "rationale": "neutral decision note",
            },
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8").lower()
    for banned in (
        "stuck",
        "spinning",
        "the agent appears",
        "the model is",
        "verdict:",
        "host judgment",
        "recommended:",
    ):
        assert banned not in body, f"timeline leaked host-authored verdict: {banned}"


def test_render_timeline_is_pure_and_handles_empty_turns() -> None:
    body = render_timeline([])
    assert "Run Timeline" in body
    # No TURN headers when no turns.
    assert "TURN" not in body


def test_timeline_renders_covered_units_per_resolution_item(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": None,
            "tool_result_raw": None,
            "resolution_state_after": {
                "items": [
                    {
                        "item_id": "p1-call-sequence",
                        "status": "in_progress",
                        "structure_kind": "group",
                        "covered_units": [
                            {
                                "unit_id": "p1-call-1-bearing",
                                "title": "Bearing N 45 E for call 1",
                                "status": "closed",
                                "determination": "earned",
                                "verification_basis": "Confirmed against source crop artifact://src-1.",
                                "evidence_refs": ["artifact://src-1"],
                            },
                            {
                                "unit_id": "p1-call-2-distance",
                                "title": "Distance 132.5 ft for call 2",
                                "status": "open",
                                "determination": "unassessed",
                            },
                        ],
                    }
                ],
            },
            "latest_refs_after": {},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "covered_units:" in body
    assert "p1-call-1-bearing | closed | earned" in body
    assert "Bearing N 45 E for call 1" in body
    assert "Confirmed against source crop artifact://src-1." in body
    assert "artifact://src-1" in body
    assert "p1-call-2-distance | open | unassessed" in body


def test_timeline_renders_covered_unit_work_graph_value_fields(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": None,
            "tool_result_raw": None,
            "resolution_state_after": {
                "items": [
                    {
                        "item_id": "parcel1-operative-call-group-source-verification",
                        "title": "Parcel 1 operative call group",
                        "kind": "claim_group",
                        "status": "in_review",
                        "structure_kind": "group",
                        "covered_units": [
                            {
                                "unit_id": "p1-nw-bearing",
                                "title": "NW corner bearing",
                                "label": "NW corner bearing",
                                "value_kind": "bearing",
                                "status": "open",
                                "candidate_values": ["N.2\u00b000'W.", "N.4\u00b000'W."],
                                "materiality": "mapping_critical",
                            },
                            {
                                "unit_id": "p1-nw-distance",
                                "title": "NW corner distance",
                                "label": "NW corner distance",
                                "value_kind": "distance",
                                "status": "closed",
                                "determination": "earned",
                                "determined_value": "1638 feet",
                                "evidence_refs": ["image:derived:crop-nw"],
                                "verification_basis": "Crop confirms the distance is 1638 feet.",
                            },
                        ],
                    }
                ],
            },
            "latest_refs_after": {},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    # Covered-unit prose/value fields still surface under Resolution Items.
    assert "value_kind:bearing" in body
    assert "candidate_values:" in body
    assert "N.2\u00b000'W." in body
    assert "1638 feet" in body
    assert "materiality:mapping_critical" in body
    assert "label: NW corner bearing" in body
    # Work Graph compact projection.
    assert "Work Graph" in body
    assert "parcel1-operative-call-group-source-verification" in body
    assert "NW corner bearing (p1-nw-bearing)" in body
    assert "candidates: N.2\u00b000'W.; N.4\u00b000'W." in body
    assert "determined: none" in body
    assert "NW corner distance (p1-nw-distance)" in body
    assert "determined: 1638 feet" in body
    assert "evidence: image:derived:crop-nw" in body


def test_timeline_renders_top_level_item_work_graph_value_fields(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": None,
            "tool_result_raw": None,
            "resolution_state_after": {
                "items": [
                    {
                        "item_id": "parcel1-bearing",
                        "title": "Parcel 1 bearing",
                        "kind": "claim",
                        "status": "closed",
                        "determination": "earned",
                        "label": "P1 bearing",
                        "value_kind": "bearing",
                        "candidate_values": ["N.2\u00b000'W.", "N.4\u00b000'W."],
                        "determined_value": "N.4\u00b000'W.",
                        "evidence_refs": ["image:derived:crop-bearing"],
                        "evidence_locators": [
                            {
                                "ref_id": "image:derived:crop-bearing",
                                "locator_kind": "image_region",
                                "box_norm": [0.1, 0.2, 0.4, 0.5],
                            }
                        ],
                    }
                ],
            },
            "latest_refs_after": {},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "Work Graph" in body
    assert "parcel1-bearing" in body
    assert "label: P1 bearing" in body
    assert "value_kind: bearing" in body
    assert "candidates: N.2\u00b000'W.; N.4\u00b000'W." in body
    assert "determined: N.4\u00b000'W." in body
    assert "evidence: image:derived:crop-bearing" in body
    assert "evidence_locators: 1 (image_region)" in body


def test_timeline_renders_saved_artifact_payload_section(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    draft_payload = {
        "source_lane": {
            "text": "Observed source text with a visible gap marker near the end.",
        },
        "downstream_lane": {
            "text": "Consumer-ready text after a downstream normalization step.",
        },
        "open_issues": [
            {
                "issue_id": "scope-gap",
                "summary": "A visible source segment remains unavailable.",
                "scope": "segment-a",
                "blocking": True,
            }
        ],
        "decision_notes": [
            {"prompt_id": "hitl-1", "decision": "Use the normalized downstream lane for export."},
        ],
        "evidence_refs": ["artifact://source"],
    }
    writer.observe_turn_completed(
        {
            "turn_index": 4,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {
                    "draft_payload": draft_payload,
                    "rationale": "save verified parcel 1 verbatim + mapping view",
                },
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "transcript_edit_working"},
                "artifact_refs": ["transcript_edit:working:rev:0003", "transcript_edit:working"],
                "refusal": None,
            },
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "Saved Artifact" in body
    assert "transcript_edit:working:rev:0003" in body
    assert "artifact_kind: transcript_edit_working" in body
    assert "draft_payload_keys: source_lane, downstream_lane, open_issues, decision_notes, evidence_refs" in body
    assert "source_lane.text:" in body
    assert "Observed source text" in body
    assert "downstream_lane.text:" in body
    assert "Consumer-ready text" in body
    assert "open_issues:" in body
    assert "scope-gap" in body
    assert "decision_notes:" in body
    assert "hitl-1" in body
    assert "evidence_refs:" in body
    assert "artifact://source" in body


def test_timeline_renders_saved_artifact_payload_with_plain_string_lanes(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    draft_payload = {
        "source_lane": "Observed source text in a single plain string lane.",
        "downstream_lane": "Consumer-ready text in a single plain string lane.",
    }
    writer.observe_turn_completed(
        {
            "turn_index": 2,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {"draft_payload": draft_payload, "rationale": "save"},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "transcript_edit_working"},
                "artifact_refs": ["transcript_edit:working:rev:0002"],
                "refusal": None,
            },
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "source_lane:" in body
    assert "Observed source text in a single plain string lane." in body
    assert "downstream_lane:" in body
    assert "Consumer-ready text in a single plain string lane." in body
    assert "source_lane: none" not in body
    assert "downstream_lane: none" not in body


def test_timeline_run_summary_shows_duration_and_final_artifact_projection(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 2,
            "parse_ok": True,
            "started_at_epoch_seconds": 100.0,
            "finished_at_epoch_seconds": 104.0,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {
                    "draft_payload": {
                        "source_lane": {"text": "Source lane text."},
                        "downstream_lane": {"text": "Normalized lane text."},
                        "notes": [{"note_id": "missing-continuation"}],
                        "evidence_refs": ["artifact://source"],
                    }
                },
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 2,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {
                    "draft_payload": {
                        "source_lane": {"text": "Source lane text."},
                        "downstream_lane": {"text": "Normalized lane text."},
                        "notes": [{"note_id": "missing-continuation"}],
                        "evidence_refs": ["artifact://source"],
                    }
                },
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "transcript_edit_working"},
                "artifact_refs": ["transcript_edit:working:rev:0005", "transcript_edit:working"],
                "refusal": None,
            },
            "latest_refs_after": {"transcript_edit:working": "transcript_edit:working:rev:0005"},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "## Run Summary" in body
    assert "## Final Run Summary" in body
    assert body.index("## Run Summary") < body.index("TURN 0002")
    assert body.rindex("## Final Run Summary") > body.index("TURN 0002")
    assert "terminal_class: in_progress" in body
    assert "total_run_duration: 4.0s" in body
    assert "latest_artifact_refs:" in body
    assert "transcript_edit:working: transcript_edit:working:rev:0005" in body
    assert body.count("## Final Artifact Projection") == 2
    assert "- posture: working" in body
    assert "- latest_artifact_ref: transcript_edit:working:rev:0005" in body
    assert "payload_keys:" in body
    assert "source_lane: present" in body
    assert "downstream_lane: present" in body
    assert "- source_lane.text:" in body
    assert "Source lane text." in body
    assert "- downstream_lane.text:" in body
    assert "Normalized lane text." in body
    assert "TURN 0002 | choose_action | save_workspace_artifact | patch:applied | duration:4.0s" in body


def test_timeline_final_projection_uses_source_revision_payload_after_publish(
    tmp_path: Path,
) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    draft_payload = {
        "source_lane": {"text": "Published source lane text."},
        "downstream_lane": {"text": "Published downstream lane text."},
    }
    writer.observe_turn_completed(
        {
            "turn_index": 4,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {"draft_payload": draft_payload},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "transcript_edit_working"},
                "artifact_refs": ["transcript_edit:working:rev:0007", "transcript_edit:working"],
                "refusal": None,
            },
            "latest_refs_after": {"transcript_edit:working": "transcript_edit:working:rev:0007"},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 5,
            "tool_request": {
                "action_type": "publish_workspace_artifact",
                "action_inputs": {"source_revision_ref": "transcript_edit:working:rev:0007"},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {
                    "output_ref": "transcript_edit:output",
                    "source_revision_ref": "transcript_edit:working:rev:0007",
                },
                "artifact_refs": ["transcript_edit:output", "transcript_edit:working:rev:0007"],
                "refusal": None,
            },
            "latest_refs_after": {"transcript_edit:output": "transcript_edit:output"},
            "state_patch_feedback": {"outcome": "no_patch"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    bottom = body[body.rindex("## Final Run Summary") :]
    assert "- posture: published" in bottom
    assert "- latest_artifact_ref: transcript_edit:output" in bottom
    assert "- source_lane.text:" in bottom
    assert "Published source lane text." in bottom
    assert "- downstream_lane.text:" in bottom
    assert "Published downstream lane text." in bottom


def test_timeline_final_projection_reads_payload_from_single_action_batch(
    tmp_path: Path,
) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    draft_payload = {
        "source_transcript_verbatim": "Verbatim source lane with Range Seventy-four.",
        "normalized_or_mapping_transcript": "Normalized mapping lane with Range Seventy-five.",
        "issues": [
            {
                "issue_id": "range_reference_conflict",
                "layer": "layer_2_intrinsic_source_integrity",
                "mapping_blocking": False,
                "scope": "document",
                "summary": "Source ranges disagree.",
                "downstream_disposition": "Normalize only the mapping lane.",
            }
        ],
        "hitl_decisions": [
            {
                "prompt_id": "hitl-range",
                "choice": "Use Range 75",
                "note": "Human adjudication for mapping lane.",
            }
        ],
        "parcel_metadata": {
            "parcels": [
                {
                    "parcel_id": "parcel_1",
                    "forwardable": True,
                    "forwardable_scope": "full visible parcel",
                    "governing_range": "Range Seventy-five (75) West",
                    "notes": ["Verbatim lane preserves source wording."],
                }
            ]
        },
        "evidence_refs": ["image:assoc:source"],
    }
    writer.observe_turn_completed(
        {
            "turn_index": 4,
            "parsed_action_plan": {
                "actions": [
                    {
                        "alias": "save_working",
                        "action_type": "save_workspace_artifact",
                        "action_inputs": {"draft_payload": draft_payload},
                    }
                ]
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "transcript_edit_working"},
                "artifact_refs": ["transcript_edit:working:rev:0001", "transcript_edit:working"],
                "refusal": None,
            },
            "latest_refs_after": {"transcript_edit:working": "transcript_edit:working:rev:0001"},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 5,
            "parsed_action_plan": {
                "actions": [
                    {
                        "alias": "publish_output",
                        "action_type": "publish_workspace_artifact",
                        "action_inputs": {"source_revision_ref": "transcript_edit:working:rev:0001"},
                    }
                ]
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {
                    "output_ref": "transcript_edit:output",
                    "source_revision_ref": "transcript_edit:working:rev:0001",
                },
                "artifact_refs": ["transcript_edit:output", "transcript_edit:working:rev:0001"],
                "refusal": None,
            },
            "latest_refs_after": {"transcript_edit:output": "transcript_edit:output"},
            "state_patch_feedback": {"outcome": "no_patch"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    bottom = body[body.rindex("## Final Run Summary") :]
    assert "- posture: published" in bottom
    assert "- source_transcript_verbatim:" in bottom
    assert "Verbatim source lane with Range Seventy-four." in bottom
    assert "- normalized_or_mapping_transcript:" in bottom
    assert "Normalized mapping lane with Range Seventy-five." in bottom
    assert "- issues:" in bottom
    assert "range_reference_conflict | layer:layer_2_intrinsic_source_integrity" in bottom
    assert "downstream_disposition:" in bottom
    assert "- hitl_decisions:" in bottom
    assert "hitl-range: Use Range 75" in bottom
    assert "- parcel_metadata:" in bottom
    assert "parcel_1 | forwardable:true | scope:full visible parcel" in bottom
    assert "- evidence_refs:" in bottom
    assert "image:assoc:source" in bottom


def test_timeline_does_not_project_final_artifact_from_failed_save_attempt(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 3,
            "parse_ok": True,
            "started_at_epoch_seconds": 20.0,
            "finished_at_epoch_seconds": 22.0,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {
                    "draft_payload": {
                        "source_lane": {"text": "Attempted source lane."},
                    }
                },
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 3,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {
                    "draft_payload": {
                        "source_lane": {"text": "Attempted source lane."},
                    }
                },
            },
            "tool_result_raw": {
                "execution_state": "refused",
                "outputs": {},
                "artifact_refs": [],
                "refusal": {"reason_code": "write_blocked"},
            },
            "latest_refs_after": {"older": "artifact://older"},
            "state_patch_feedback": {"outcome": "no_patch"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "## Final Artifact Projection" not in body
    assert "## Final Run Summary" in body
    assert "Saved Artifact" not in body


def test_timeline_final_projection_scans_all_payload_entries_for_text_lanes(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    draft_payload = {
        "metadata": {"status": "working"},
        "provenance": {"source": "scanner-a"},
        "notes": [{"note_id": "n1"}],
        "evidence_refs": ["artifact://source"],
        "source_lane": {"text": "Observed source text after metadata keys."},
        "downstream_lane": {"text": "Consumer-ready text after metadata keys."},
    }
    writer.observe_llm_io(
        {
            "turn_index": 5,
            "parse_ok": True,
            "started_at_epoch_seconds": 30.0,
            "finished_at_epoch_seconds": 31.0,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {"draft_payload": draft_payload},
            },
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 5,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {"draft_payload": draft_payload},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "generic_working"},
                "artifact_refs": ["artifact://final"],
                "refusal": None,
            },
            "latest_refs_after": {"final": "artifact://final"},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert body.count("## Final Artifact Projection") == 2
    bottom = body[body.rindex("## Final Run Summary") :]
    assert "- source_lane.text:" in body
    assert "Observed source text after metadata keys." in body
    assert "- downstream_lane.text:" in body
    assert "Consumer-ready text after metadata keys." in body
    assert "- source_lane.text:" in bottom
    assert "Observed source text after metadata keys." in bottom
    assert "- downstream_lane.text:" in bottom
    assert "Consumer-ready text after metadata keys." in bottom


def test_timeline_final_projection_renders_generic_text_bearing_payload_fields(
    tmp_path: Path,
) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    draft_payload = {
        "metadata": {"status": "working", "revision": 3},
        "opaque_notes": [{"note_id": "n1"}],
        "alpha_payload": {"text": "First generic text lane with no domain-specific name."},
        "omega_narrative": "Second generic text lane in a plain string field.",
    }
    writer.observe_turn_completed(
        {
            "turn_index": 6,
            "tool_request": {
                "action_type": "save_workspace_artifact",
                "action_inputs": {"draft_payload": draft_payload},
            },
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {"artifact_kind": "generic_working"},
                "artifact_refs": ["artifact://generic-final"],
                "refusal": None,
            },
            "latest_refs_after": {"final": "artifact://generic-final"},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    bottom = body[body.rindex("## Final Run Summary") :]
    assert "alpha_payload: present" in bottom
    assert "omega_narrative: present" in bottom
    assert "- alpha_payload.text:" in bottom
    assert "First generic text lane with no domain-specific name." in bottom
    assert "- omega_narrative:" in bottom
    assert "Second generic text lane in a plain string field." in bottom
    assert "source_transcript_verbatim" not in body
    assert "normalized_or_mapping_transcript" not in body
    assert "parcel_metadata" not in body


def test_timeline_rewrites_earlier_turn_sections_when_updated(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "tool_request": {"action_type": "first_action", "action_inputs": {}},
        }
    )
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": {"action_type": "first_action", "action_inputs": {}},
            "tool_result_raw": {
                "execution_state": "executed",
                "outputs": {},
                "artifact_refs": [],
                "refusal": None,
            },
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    # One TURN 0001 section, now updated with the execution result.
    assert body.count("TURN 0001") == 1
    assert "first_action" in body
    assert "execution_state: executed" in body


def test_timeline_renders_user_message_ledger(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed(
        {
            "turn_index": 1,
            "tool_request": None,
            "tool_result_raw": None,
            "user_message_ledger": [
                {
                    "message_id": "user-msg-1",
                    "status": "pending",
                    "source": "tester",
                    "text": "The value in atom x should be reviewed.",
                    "_bounds": {"text_truncated": True},
                },
                {
                    "message_id": "user-msg-2",
                    "status": "deferred",
                    "source": "ui",
                    "text": "Handle later",
                    "defer_reason": "out of scope for this turn",
                },
            ],
            "user_message_consumed_unknown_count": 1,
            "latest_refs_after": {},
            "state_patch_feedback": {"outcome": "applied"},
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "User Messages" in body
    assert "consumed_unknown_count: 1" in body
    assert "message_id: user-msg-1" in body
    assert "status: pending" in body
    assert "source: tester" in body
    assert "The value in atom x should be reviewed." in body
    assert "text_truncated" in body
    assert "defer_reason:" in body
    assert "out of scope for this turn" in body


def test_timeline_renders_performance_evaluation_section(tmp_path: Path) -> None:
    writer = RunAuditWriter(tmp_path / "run1")
    writer.observe_llm_io(
        {
            "turn_index": 1,
            "parse_ok": True,
            "prompt_observability_summary": {
                "performance_evaluation": {
                    "accuracy_status": "not_live_scored",
                    "work_graph": {
                        "work_units_total": 5,
                        "closed_units": 2,
                        "open_units": 3,
                        "blocked_units": 1,
                    },
                    "productivity": {
                        "determinations_changed_total": 2,
                        "units_closed_total": 1,
                        "determinations_per_turn": 2.0,
                        "units_closed_per_turn": 1.0,
                    },
                    "current_pressure": ["accuracy_not_live_scored"],
                }
            },
        }
    )
    body = _timeline_path(tmp_path / "run1").read_text(encoding="utf-8")
    assert "Performance evaluation:" in body
    assert "accuracy: not live scored" in body
    assert "work graph: 5 total / 2 closed / 3 open / 1 blocked" in body


def test_timeline_renders_source_window_line_for_crop(tmp_path: Path) -> None:
    body = render_timeline(
        [
            {
                "turn_index": 2,
                "parse_ok": True,
                "tool_result_raw": {
                    "execution_state": "executed",
                    "artifact_refs": ["image:derived:crop-1"],
                    "outputs": {
                        "derived_ref_id": "image:derived:crop-1",
                        "parent_ref_id": "image:assoc:tx-1:original",
                        "sub_action": "crop",
                        "source_window": {
                            "position_label": "bottom_full_width",
                            "touches_source_edge": {
                                "left": True,
                                "top": False,
                                "right": True,
                                "bottom": True,
                            },
                            "room_to_source_edge_norm": {
                                "left": 0.0,
                                "top": 0.8,
                                "right": 0.0,
                                "bottom": 0.0,
                            },
                            "can_expand": {
                                "left": False,
                                "up": True,
                                "right": False,
                                "down": False,
                            },
                        },
                    },
                },
            }
        ]
    )
    assert "source_window:" in body
    assert "bottom_full_width" in body
    assert "can_expand_down=false" in body


def test_tool_result_renders_resolvable_image_refs_as_links(tmp_path: Path, monkeypatch) -> None:
    from harness.audit.artifact_ref_links import ArtifactLinkContext
    from harness.audit.human_timeline import _render_tool_result

    png_dir = tmp_path / "feature_graphs" / "d1" / "mappings" / "map1"
    png_dir.mkdir(parents=True)
    (png_dir / "clean.png").write_bytes(b"png")

    timeline_path = tmp_path / "audit" / "human" / "timeline.md"
    timeline_path.parent.mkdir(parents=True)
    ref = "artifact://dossiers/feature_graphs/d1/mappings/map1/clean.png"
    monkeypatch.setattr(
        "harness.audit.artifact_ref_links.dossiers_artifacts_root",
        lambda: tmp_path,
    )
    context = ArtifactLinkContext(timeline_path=timeline_path, ref_path_index={})
    turn = {
        "tool_result_raw": {
            "execution_state": "executed",
            "artifact_refs": [ref, "feature_graph:mapping:map1"],
            "outputs": {
                "rendered_feature_count": 2,
                "skipped_feature_count": 0,
            },
            "image_evidence": [{"ref_id": ref, "media_type": "image/png", "b64": "cG5n"}],
        }
    }
    body = "\n".join(_render_tool_result(turn, link_context=context))
    assert ref in body
    assert "[open image]" in body
    assert "image_evidence_count: 1" in body
    assert "rendered_feature_count" in body
