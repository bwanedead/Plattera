"""Tests for unintegrated delegate observation worklist projection."""

from __future__ import annotations

import json

from harness.runtime.memory.delegate_observation_worklist import build_delegate_observation_worklist
from domains.mapping.transcript_edit.execution.delegate_observation_reminder import (
    TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER,
)
from harness.runtime.memory.delegate_observation_worklist_projection import (
    GENERIC_DELEGATE_OBSERVATION_REMINDER,
    build_delegate_observation_worklist_for_prompt,
    compact_delegate_observation_worklist_for_prompt,
    delegate_observation_reminder_from_context,
    resolve_delegate_observation_reminder,
)
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.prompt_packet_builder import _compact_prompt_observability_summary
from harness.runtime.orchestration.subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from harness.runtime.orchestration.subtasks.delegate_result_refs import build_delegate_result_record


def _completed_record(
    *,
    turn: int = 14,
    alias: str = "read_p1_call3",
    ref_id: str | None = None,
    profile: str = "transcript_edit.visual_source_observation",
    context_refs: list[str] | None = None,
    result: dict | None = None,
    trace: dict | None = None,
    target_entity_id: str | None = None,
) -> dict:
    action_inputs = {
        "profile": profile,
        "task": "Read bearing text from crop.",
        "context_refs": context_refs or ["image:derived:crop-p1"],
    }
    if target_entity_id:
        action_inputs["target_entity_id"] = target_entity_id
    record = build_delegate_result_record(
        ref_id=ref_id or f"subtask:turn{turn}:{alias}",
        turn_index=turn,
        alias=alias,
        action_index=1,
        action_inputs=action_inputs,
        outputs={
            "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
            "subtask_id": alias,
            "status": "completed",
            "profile": profile,
            "input_refs": context_refs or ["image:derived:crop-p1"],
            "result": result
            or {
                "task_response": "thence S. 4° 00' E.",
                "source_visible_text": "said parcel of land",
                "ambiguity": "",
                "limits": ["crop edge clipped"],
            },
            "subtask_trace": trace
            or {
                "total_seconds": 132.2,
                "model_call_seconds": 132.0,
                "retry_count": 0,
                "prompt_char_count": 4195,
                "image_attachment_count": 1,
                "raw_prompt_text": "strip me",
                "b64": "strip me",
            },
        },
    )
    return record


def test_unintegrated_completed_delegate_appears_in_worklist() -> None:
    record = _completed_record(target_entity_id="p1_call3_bearing")
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        resolution_state={"items": []},
    )
    assert worklist["counts"]["unintegrated_completed"] == 1
    row = worklist["rows"][0]
    assert row["ref_id"] == "subtask:turn14:read_p1_call3"
    assert row["target_entity_id"] == "p1_call3_bearing"
    assert row["source_visible_text_preview"] == "said parcel of land"
    assert row["subtask_trace"]["total_seconds"] == 132.2


def test_delegate_ref_in_resolution_evidence_refs_is_integrated() -> None:
    record = _completed_record()
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        resolution_state={
            "items": [
                {
                    "item_id": "bearing-1",
                    "evidence_refs": ["subtask:turn14:read_p1_call3"],
                }
            ]
        },
    )
    assert worklist["counts"]["unintegrated_completed"] == 0
    assert worklist["rows"] == []


def test_delegate_ref_nested_in_mission_state_counts_as_integrated() -> None:
    record = _completed_record(ref_id="subtask:turn9:read_a")
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        mission_state={
            "notes": {
                "integrated_refs": ["subtask:turn9:read_a"],
            }
        },
    )
    assert worklist["rows"] == []


def test_repair_bundle_reference_excludes_from_worklist() -> None:
    record = _completed_record(ref_id="subtask:turn11:read_b")
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        repair_bundle={
            "fragments": [
                {"ref_id": "subtask:turn11:read_b", "path": "resolution.items[0].evidence_refs"},
            ]
        },
    )
    assert worklist["rows"] == []


def test_context_crop_ref_in_state_excludes_from_worklist() -> None:
    crop_ref = "image:derived:crop-p1_call3"
    record = _completed_record(
        ref_id="subtask:turn14:read_p1_call3",
        context_refs=[crop_ref],
    )
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        resolution_state={
            "items": [
                {
                    "item_id": "bearing-1",
                    "evidence_refs": [crop_ref],
                }
            ]
        },
    )
    assert worklist["counts"]["unintegrated_completed"] == 0
    assert worklist["rows"] == []


def test_context_crop_ref_in_repair_bundle_excludes_from_worklist() -> None:
    crop_ref = "image:derived:crop-p1_call3"
    record = _completed_record(
        ref_id="subtask:turn14:read_p1_call3",
        context_refs=[crop_ref],
    )
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        repair_bundle={
            "fragments": [
                {"evidence_refs": [crop_ref]},
            ]
        },
    )
    assert worklist["rows"] == []


def test_similar_crop_ref_does_not_integrate() -> None:
    record = _completed_record(
        context_refs=["image:derived:crop-p1_call3"],
    )
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        resolution_state={
            "items": [{"evidence_refs": ["image:derived:crop-p1_call3_extra"]}],
        },
    )
    assert worklist["counts"]["unintegrated_completed"] == 1


def test_non_completed_delegate_status_ignored() -> None:
    record = _completed_record()
    record["status"] = "failed"
    worklist = build_delegate_observation_worklist(delegate_result_records=[record])
    assert worklist["rows"] == []


def test_preview_caps_and_sensitive_fields_stripped() -> None:
    long_text = "x" * 500
    record = _completed_record(
        result={
            "task_response": long_text,
            "source_visible_text": long_text,
        },
        context_refs=["C:\\secret\\path.png", "image:derived:ok"],
    )
    worklist = build_delegate_observation_worklist(delegate_result_records=[record])
    row = worklist["rows"][0]
    assert len(row["task_response_preview"]) <= 300
    assert row["context_refs"] == ["image:derived:ok"]
    serialized = json.dumps(worklist)
    assert "b64" not in serialized
    assert "raw_prompt_text" not in serialized
    assert "C:\\secret" not in serialized


def test_no_fuzzy_alias_matching() -> None:
    record = _completed_record(alias="read_p1_call3", ref_id="subtask:turn14:read_p1_call3")
    worklist = build_delegate_observation_worklist(
        delegate_result_records=[record],
        resolution_state={
            "items": [{"item_id": "x", "notes": "read_p1_call3 mentioned but not exact ref"}],
        },
    )
    assert worklist["counts"]["unintegrated_completed"] == 1


def test_prompt_projection_uses_generic_reminder_by_default() -> None:
    record = _completed_record()
    projected = build_delegate_observation_worklist_for_prompt(
        delegate_result_records=[record],
    )
    assert projected is not None
    assert projected["reminder"] == GENERIC_DELEGATE_OBSERVATION_REMINDER
    assert "opportunistically harvest" not in projected["reminder"]


def test_prompt_projection_accepts_domain_injected_reminder_override() -> None:
    record = _completed_record()
    projected = build_delegate_observation_worklist_for_prompt(
        delegate_result_records=[record],
        reminder=TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER,
    )
    assert projected is not None
    assert projected["reminder"] == TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER
    assert "opportunistically harvest" in projected["reminder"]


def test_delegate_observation_reminder_from_context_reads_opaque_key() -> None:
    assert delegate_observation_reminder_from_context(
        {"delegate_observation_worklist_reminder": TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER}
    ) == TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER
    assert resolve_delegate_observation_reminder(None) == GENERIC_DELEGATE_OBSERVATION_REMINDER


def test_loop_health_summary_uses_context_reminder_override() -> None:
    from harness.runtime.memory import LoopMemoryState

    loop_memory = LoopMemoryState()
    loop_memory.iterations = 15
    loop_memory.continuity.delegate_subtask_results = [_completed_record()]
    summary = build_prompt_observability_summary(
        loop_memory,
        delegate_observation_worklist_reminder=TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER,
    )
    block = summary.get("delegate_observation_worklist")
    assert isinstance(block, dict)
    assert block["reminder"] == TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER


def test_prompt_projection_omitted_when_no_unintegrated_rows() -> None:
    record = _completed_record()
    projected = build_delegate_observation_worklist_for_prompt(
        delegate_result_records=[record],
        resolution_state={
            "items": [{"evidence_refs": ["subtask:turn14:read_p1_call3"]}],
        },
    )
    assert projected is None


def test_prompt_compaction_keeps_delegate_observation_worklist() -> None:
    record = _completed_record()
    projected = build_delegate_observation_worklist_for_prompt(
        delegate_result_records=[record],
    )
    assert projected is not None
    compact = compact_delegate_observation_worklist_for_prompt(projected)
    assert compact is not None
    assert compact["reminder"]
    assert compact["rows"]

    summary = {
        "resolution_item_count": 1,
        "delegate_observation_worklist": projected,
        "performance_evaluation": {"schema_version": 1},
    }
    prompt_compact = _compact_prompt_observability_summary(summary)
    block = prompt_compact["delegate_observation_worklist"]
    assert block["counts"]["unintegrated_completed"] == 1
    assert block["rows"]


def test_loop_health_summary_surfaces_delegate_observation_worklist() -> None:
    from harness.runtime.memory import LoopMemoryState

    loop_memory = LoopMemoryState()
    loop_memory.iterations = 15
    loop_memory.continuity.delegate_subtask_results = [_completed_record()]
    summary = build_prompt_observability_summary(loop_memory)
    block = summary.get("delegate_observation_worklist")
    assert isinstance(block, dict)
    assert block["counts"]["unintegrated_completed"] == 1
    assert block["rows"]
