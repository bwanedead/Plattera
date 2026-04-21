from __future__ import annotations

from pathlib import Path

from harness.audit.human_timeline import render_timeline
from harness.audit.run_audit_writer import RunAuditWriter


TIMELINE_REL = ("audit", "human", "timeline.md")


def _timeline_path(run_dir: Path) -> Path:
    return run_dir.joinpath(*TIMELINE_REL)


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
    assert "RATIONALE_PROSE" in body
    assert "OPERATOR_STATUS_LINE" in body
    assert "CONT_JOURNAL_TEXT" in body
    assert "HITL_PROMPT_MESSAGE" in body
    assert "Option A" in body
    assert "HITL_CONTEXT_NOTES" in body


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
    assert "work_state: investigating" in body
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
