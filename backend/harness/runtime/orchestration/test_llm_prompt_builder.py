from __future__ import annotations

import json
from typing import Any

from harness.execution.session import ExecutionSessionManager
from harness.mission_state import new_closure_state, new_mission_state, new_resolution_state
from harness.runtime.composition.contracts import ComposedTurnInput, TurnBlock
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.continuity_journal import wrap_journal_entry
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import (
    build_choose_action_prompt_document,
    build_compaction_prompt_document,
    build_repair_prompt_document,
    build_resume_prompt_document,
)


def _composed_input() -> ComposedTurnInput:
    return ComposedTurnInput(
        blocks=(
            TurnBlock(
                content="stable doctrine",
                metadata={"harness.prompt_block": {"layer": "harness_trunk", "block_id": "harness_trunk"}},
            ),
            TurnBlock(
                content="startup inventory",
                metadata={"test.prompt_block": {"layer": "domain_startup_context", "block_id": "startup"}},
            ),
        ),
        surface_payloads={
            "domain": {
                "tool_specs": [
                    {
                        "tool_id": "noop",
                        "category": "read",
                        "purpose": "Do one bounded check.",
                        "expected_request_shape": "empty object",
                    }
                ]
            }
        },
        tool_handlers={"noop": lambda payload: payload},
    )


def _context(*, iterations: int = 3) -> OrchestratorContext:
    loop_memory = LoopMemoryState()
    loop_memory.iterations = iterations
    loop_memory.continuity.latest_refs = {"draft": "ref://draft"}
    loop_memory.continuity.active_item_id = "item-1"
    loop_memory.continuity.state_patch_feedback = {"outcome": "applied"}
    loop_memory.continuity.compacted_continuity_summary = "older turns folded"
    loop_memory.continuity.continuity_journal_entries.extend(
        [
            wrap_journal_entry(kernel_turn_index=1, author_payload={"step": "first"}),
            wrap_journal_entry(kernel_turn_index=2, author_payload={"step": "second"}),
        ]
    )
    loop_memory.continuity.kernel_step_records.extend(
        [
            {"kernel_turn_index": 1, "action_type": "noop", "execution_state": "skipped"},
            {"kernel_turn_index": 2, "action_type": "noop", "execution_state": "executed"},
        ]
    )
    loop_memory.continuity.kernel_step_result_records.append(
        {
            "kernel_turn_index": 2,
            "action_type": "noop",
            "execution_state": "executed",
            "artifact_refs": [],
            "latest_refs_snapshot": {"draft": "ref://draft"},
            "outputs_for_continuity": {"note": "done"},
            "result_truncated": False,
        }
    )
    return OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-prompt",
        loop_memory=loop_memory,
        request_id_prefix="req-prompt",
        opaque_run_context={},
        prompt_event_observer=None,
        raw_llm_io_observer=None,
    )


def _projection() -> SharedStateProjection:
    resolution_state = new_resolution_state(
        items=[{"item_id": "item-1", "title": "Check the draft", "kind": "review", "status": "open"}],
        updated_at_epoch_seconds=42.0,
    )
    mission_state = new_mission_state(
        mission_id="mission-1",
        loop_family="orchestration_kernel",
        objective="Verify the draft truthfully.",
        resolution_state=resolution_state,
        closure_state=new_closure_state(
            overall_status="in_review",
            updated_at_epoch_seconds=42.0,
            dimensions=[
                {
                    "dimension_id": "layer_1",
                    "title": "Delta convergence",
                    "status": "open",
                    "summary": "Still unresolved.",
                }
            ],
        ),
        updated_at_epoch_seconds=42.0,
    )
    return SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs={"draft": "ref://draft"},
        active_item_id="item-1",
    )


def test_full_choose_action_prompt_document_separates_layers() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1", "max_iterations": 9},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )

    assert doc.mode == "full_choose_action"
    assert doc.prompt_body["prompt_mode"] == "full_choose_action"
    assert len(doc.prompt_body["doctrine_blocks"]) == 1
    assert doc.prompt_body["surface_packet"]["blocks"][0]["content"] == "startup inventory"
    assert doc.prompt_body["surface_packet"]["tool_ids"] == ["noop"]
    assert "run_context" in doc.prompt_body
    assert "structured_state" in doc.prompt_body
    projection_blob = json.dumps(doc.prompt_body["run_context"]["projection"], ensure_ascii=False, sort_keys=True)
    assert "schema_version" not in projection_blob
    assert "updated_at_epoch_seconds" not in projection_blob
    assert "max_iterations" not in doc.prompt_text
    prompt_text = doc.prompt_text.lower()
    assert "what would count as earned proof rather than provisional belief" in prompt_text
    assert "thin ledger that covers only a few disagreements is usually not enough" in prompt_text
    assert "if no stronger in-run check remains for a material unresolved item" in prompt_text


def test_repair_prompt_document_is_mode_explicit_and_thinner_than_full() -> None:
    full_doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    repair_doc = build_repair_prompt_document(
        available_tool_ids=("noop",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail="model output was not valid JSON",
        previous_response_text="not-json",
    )

    assert repair_doc.mode == "repair"
    assert repair_doc.prompt_body["prompt_mode"] == "repair"
    assert "doctrine_blocks" not in repair_doc.prompt_body
    assert repair_doc.prompt_body["surface_packet"]["tool_ids"] == ["noop"]
    assert repair_doc.prompt_body["repair_context"]["prior_prompt_mode"] == "full_choose_action"
    assert len(repair_doc.prompt_text) < len(full_doc.prompt_text)


def test_resume_prompt_document_is_explicit_and_slimmer_than_full() -> None:
    context = _context()
    context.loop_memory.hitl.hitl_state = "answered_unintegrated"
    context.loop_memory.hitl.answered_hitl_responses.append(
        {"prompt_id": "p-1", "feedback": {"message": "Continue with the north edge."}}
    )
    full_doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=context,
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    resume_doc = build_resume_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=context,
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )

    assert resume_doc.mode == "resume"
    assert resume_doc.prompt_body["prompt_mode"] == "resume"
    assert "answered_hitl_responses" in resume_doc.prompt_body["run_context"]
    assert "recent_kernel_step_records" not in resume_doc.prompt_body["structured_state"]
    assert "recent_kernel_step_result_records" not in resume_doc.prompt_body["structured_state"]
    assert len(resume_doc.prompt_text) < len(full_doc.prompt_text)


def test_compaction_prompt_document_uses_explicit_mode_packet() -> None:
    doc = build_compaction_prompt_document(
        prior_compacted_continuity_summary="older summary",
        journal_entries_to_fold=[{"kernel_turn_index": 1, "author_payload": {"step": "alpha"}}],
        kernel_step_records_to_fold=[{"kernel_turn_index": 1, "execution_state": "skipped"}],
        kernel_step_result_records_to_fold=[],
        target_compacted_summary_chars=900,
    )

    assert doc.mode == "compaction"
    assert doc.prompt_body["prompt_mode"] == "compaction"
    assert "doctrine_blocks" not in doc.prompt_body
    assert "surface_packet" not in doc.prompt_body
    assert doc.prompt_body["compaction_context"]["target_compacted_summary_chars"] == 900
