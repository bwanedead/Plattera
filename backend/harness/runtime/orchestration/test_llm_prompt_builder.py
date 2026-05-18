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
    build_state_repair_prompt_document,
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
    # Semantic doctrine strings ("what would count as earned proof...", "thin ledger...",
    # "if no stronger in-run check remains...") were moved to surface.py TurnBlocks.
    # The mechanical instruction text now carries only envelope contract content.
    assert "no-dispatch state-authoring turns are valid" in prompt_text
    assert "state_patch_feedback" in prompt_text
    assert "closure_state dimensions merge by `dimension_id`" in prompt_text


def test_full_choose_action_prompt_uses_slim_turn_timeline_instead_of_raw_recent_arrays() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )

    structured_state = doc.prompt_body["structured_state"]
    assert "recent_turn_timeline" in structured_state
    assert "recent_kernel_step_records" not in structured_state
    assert "recent_kernel_step_result_records" not in structured_state
    assert "recent_continuity_journal_entries" in structured_state

    timeline = structured_state["recent_turn_timeline"]
    assert isinstance(timeline, list) and timeline
    first = timeline[0]
    for key in (
        "kernel_turn_index",
        "action_type",
        "execution_state",
        "skip_execution",
        "wait_for_human",
        "complete_run",
        "latest_refs_changed",
        "result_truncated",
        "artifact_ref_count",
    ):
        assert key in first


def test_full_choose_action_projection_has_single_resolution_state_copy() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    projection_blob = doc.prompt_body["run_context"]["projection"]
    assert "resolution_state" in projection_blob
    assert "resolution_state" not in projection_blob["mission_state"]


def test_state_repair_prompt_carries_lean_structured_state_and_richer_run_context() -> None:
    """state_repair uses lean structured_state (no bulky step-record arrays) but keeps
    the richer run_context anchors (session_id, latest_refs, active_item_id, etc.)."""
    doc = build_state_repair_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    structured_state = doc.prompt_body["structured_state"]
    assert doc.mode == "state_repair"
    # Bulky raw step-record arrays are excluded from state_repair to keep closure-repair
    # prompts lean; tool result slices and timeline provide equivalent signal.
    assert "recent_kernel_step_records" not in structured_state
    assert "recent_kernel_step_result_records" not in structured_state
    # Lean fields are still present.
    assert "recent_turn_timeline" in structured_state
    assert "recent_tool_result_slices" in structured_state
    assert "recent_continuity_journal_entries" in structured_state
    # state_repair still carries the richer run_context anchors.
    run_context = doc.prompt_body["run_context"]
    for expected_key in (
        "session_id",
        "request_id_prefix",
        "latest_refs",
        "active_item_id",
    ):
        assert expected_key in run_context


def test_full_choose_action_run_context_drops_duplicate_transport_fields() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    run_context = doc.prompt_body["run_context"]
    for dropped_key in (
        "session_id",
        "request_id_prefix",
        "latest_refs",
        "active_item_id",
        "operator_progress_message",
    ):
        assert dropped_key not in run_context
    # Projection carries latest_refs / active_item_id as the canonical copy.
    assert "projection" in run_context
    assert "latest_refs" in run_context["projection"]


def test_resume_prompt_run_context_matches_slim_shape() -> None:
    context = _context()
    context.loop_memory.hitl.hitl_state = "answered_unintegrated"
    doc = build_resume_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=context,
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    run_context = doc.prompt_body["run_context"]
    for dropped_key in (
        "session_id",
        "request_id_prefix",
        "latest_refs",
        "active_item_id",
        "operator_progress_message",
    ):
        assert dropped_key not in run_context


def test_compact_prompt_visible_observability_drops_zero_counters() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    summary = doc.prompt_body["structured_state"]["prompt_observability_summary"]
    # Structural anchors always present.
    assert "work_universe_posture" in summary
    assert "resolution_item_count" in summary
    assert "success_condition_count" in summary
    assert "closure_dimension_count" in summary
    # Graph-shape counters must appear even when zero — zero is diagnostically
    # meaningful ("4 items, 0 atomic, 0 groups, 0 covered units").
    for graph_shape_key in (
        "atomic_item_count",
        "group_item_count",
        "covered_unit_count",
        "covered_units_with_candidates_count",
        "closed_value_units_missing_evidence_count",
        "earned_units_missing_verification_basis_count",
        "notebook_shaped_graph_rows_count",
        "artifact_claim_inventory_suspect_count",
    ):
        assert graph_shape_key in summary, f"graph-shape counter missing: {graph_shape_key}"
    # Zero-valued optional counters (non-graph-shape) must not appear.
    for dropped_key in (
        "consecutive_no_dispatch_turns",
        "turns_since_last_tool_execution",
        "turns_since_latest_refs_change",
        "sequenced_item_count",
        "closed_items_without_basis_count",
    ):
        assert dropped_key not in summary


def test_default_continuity_journal_verbatim_keep_n_is_three() -> None:
    from harness.runtime.orchestration.llm_turn_adapter import LlmTurnOrchestrationAdapter
    from harness.runtime.orchestration.llm_turn_lifecycle import LlmTurnPreChooseActionParticipant

    assert LlmTurnOrchestrationAdapter.__dataclass_fields__[
        "continuity_journal_verbatim_keep_n"
    ].default == 3
    assert LlmTurnPreChooseActionParticipant.__dataclass_fields__[
        "continuity_journal_verbatim_keep_n"
    ].default == 3


def test_full_choose_action_prompt_is_smaller_when_raw_recent_arrays_are_dropped() -> None:
    # Build the current (slim) prompt.
    slim_doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )

    # Reconstruct a hypothetical "fat" version that still carried the raw arrays
    # and a duplicated nested mission_state.resolution_state, for comparison.
    fat_body = json.loads(json.dumps(slim_doc.prompt_body))
    from harness.runtime.memory.continuity_journal import (
        recent_step_records_for_prompt,
        recent_step_result_records_for_prompt,
    )

    ctx = _context()
    fat_body["structured_state"]["recent_kernel_step_records"] = recent_step_records_for_prompt(
        ctx.loop_memory.continuity.continuity_journal_entries,
        ctx.loop_memory.continuity.kernel_step_records,
        ctx.loop_memory.continuity.kernel_step_result_records,
        keep_n=2,
    )
    fat_body["structured_state"]["recent_kernel_step_result_records"] = (
        recent_step_result_records_for_prompt(
            ctx.loop_memory.continuity.continuity_journal_entries,
            ctx.loop_memory.continuity.kernel_step_records,
            ctx.loop_memory.continuity.kernel_step_result_records,
            keep_n=2,
        )
    )
    proj = fat_body["run_context"]["projection"]
    proj["mission_state"]["resolution_state"] = proj["resolution_state"]
    fat_text = slim_doc.instruction_text + "\n\n" + json.dumps(fat_body, ensure_ascii=False)

    assert len(slim_doc.prompt_text) < len(fat_text)


def test_full_choose_action_prompt_document_preserves_stable_top_level_key_order() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1", "max_iterations": 9},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )

    prompt_payload = json.loads(doc.prompt_text.removeprefix(doc.instruction_text + "\n\n"))
    assert list(prompt_payload.keys()) == [
        "prompt_mode",
        "doctrine_blocks",
        "surface_packet",
        "run_context",
        "structured_state",
    ]


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


def test_repair_prompt_document_includes_parsed_object_when_valid_json() -> None:
    """When previous_response_text is a valid JSON object, repair context should carry
    previous_response_object and derive structural repair_targets."""
    prior_obj = {
        "action_type": "select_tool",
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": False,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": None,
        # continuity_journal_entry intentionally missing (formerly a failure trigger)
        "operator_progress_message": None,
    }
    prior_text = json.dumps(prior_obj)

    doc = build_repair_prompt_document(
        available_tool_ids=("select_tool",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail="continuity_journal_entry is required",
        previous_response_text=prior_text,
        previous_response_object=prior_obj,
        repair_targets=["add_missing_continuity_journal_entry"],
    )

    assert doc.mode == "repair"
    repair_ctx = doc.prompt_body["repair_context"]
    assert repair_ctx["previous_response_object"] == prior_obj
    assert "add_missing_continuity_journal_entry" in repair_ctx["repair_targets"]


def test_repair_prompt_document_omits_previous_response_object_when_not_provided() -> None:
    """Without a parsed object, repair context should not include the key."""
    doc = build_repair_prompt_document(
        available_tool_ids=("noop",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail="not valid json",
        previous_response_text="not-json",
    )
    assert "previous_response_object" not in doc.prompt_body["repair_context"]
    assert "repair_targets" not in doc.prompt_body["repair_context"]


def test_repair_prompt_document_includes_misplaced_closure_state_target() -> None:
    """Misplaced state_patch.closure_state should yield a relocation repair target."""
    prior_obj = {
        "action_type": None,
        "action_inputs": {},
        "idempotency_key": "ik-1",
        "skip_execution": True,
        "wait_for_human": False,
        "complete_run": False,
        "rationale": None,
        "state_patch": {
            # closure_state at top level of state_patch instead of under mission
            "closure_state": {"overall_status": "open"},
        },
        "operator_progress_message": None,
    }
    doc = build_repair_prompt_document(
        available_tool_ids=(),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail="some parse error",
        previous_response_text=json.dumps(prior_obj),
        previous_response_object=prior_obj,
        repair_targets=["move_state_patch_closure_state_under_mission"],
    )
    assert "move_state_patch_closure_state_under_mission" in doc.prompt_body["repair_context"]["repair_targets"]


def test_repair_prompt_document_derives_add_missing_rationale_target() -> None:
    """Missing rationale in the prior response and a rationale-mentioning parse error should
    drive the repair lane to surface add_missing_rationale as a structural repair target."""
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior_obj = {
        "action_type": "noop",
        "action_inputs": {},
        "state_patch": None,
    }
    prior_text = json.dumps(prior_obj)
    _, targets = _derive_repair_context(
        prior_text,
        "rationale is required on every turn: short decision note with why-this-move and expected-gain",
    )
    assert "add_missing_rationale" in targets

    doc = build_repair_prompt_document(
        available_tool_ids=("noop",),
        prior_prompt_mode="full_choose_action",
        parse_reason_code="invalid_model_action_json",
        parse_error_detail="rationale is required on every turn",
        previous_response_text=prior_text,
        previous_response_object=prior_obj,
        repair_targets=targets,
    )
    assert "add_missing_rationale" in doc.prompt_body["repair_context"]["repair_targets"]


def test_repair_prompt_document_derives_add_missing_rationale_on_blank_rationale() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior_obj = {
        "action_type": "noop",
        "action_inputs": {},
        "rationale": "   ",
        "state_patch": None,
    }
    _, targets = _derive_repair_context(
        json.dumps(prior_obj),
        "rationale must be a non-empty string explaining why this move",
    )
    assert "add_missing_rationale" in targets


def test_repair_prompt_document_does_not_derive_rationale_target_when_error_unrelated() -> None:
    from harness.runtime.orchestration.repair_lane import _derive_repair_context

    prior_obj = {
        "action_type": "noop",
        "action_inputs": {},
        "state_patch": {"closure_state": {"overall_status": "open"}},
    }
    _, targets = _derive_repair_context(
        json.dumps(prior_obj),
        "move closure_state under mission",
    )
    assert "add_missing_rationale" not in targets


def test_full_choose_action_includes_recent_tool_result_slices() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    structured = doc.prompt_body["structured_state"]
    assert "recent_tool_result_slices" in structured
    assert "recent_kernel_step_result_records" not in structured
    slices = structured["recent_tool_result_slices"]
    assert isinstance(slices, list) and slices
    entry = slices[0]
    for key in (
        "kernel_turn_index",
        "action_type",
        "execution_state",
        "result_truncated",
        "artifact_refs",
        "outputs_excerpt",
        "outputs_excerpt_truncated",
    ):
        assert key in entry
    # The previous turn's stored tool result (note=done) must be visible as bounded text.
    blob = json.dumps(entry["outputs_excerpt"], ensure_ascii=False, sort_keys=True, default=str)
    assert "done" in blob


def test_full_choose_action_prompt_body_has_slices_not_raw_records() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    prompt_text = doc.prompt_text
    assert "recent_tool_result_slices" in prompt_text
    assert "recent_kernel_step_result_records" not in prompt_text


def test_tool_result_slices_truncate_oversized_outputs() -> None:
    from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices

    big = "x" * 20000
    rows = [
        {
            "kernel_turn_index": 1,
            "action_type": "hydrate_artifact_refs",
            "execution_state": "executed",
            "execution_reason_code": None,
            "artifact_refs": [],
            "outputs_for_continuity": {"payload": big},
            "result_truncated": False,
        }
    ]
    slices = build_recent_tool_result_slices(rows, max_chars_per_result=500)
    assert len(slices) == 1
    entry = slices[0]
    excerpt = entry["outputs_excerpt"]
    excerpt_str = excerpt if isinstance(excerpt, str) else json.dumps(excerpt, default=str)
    assert len(excerpt_str) <= 500
    assert entry["outputs_excerpt_truncated"] is True


def test_tool_result_slices_strip_binary_image_payloads() -> None:
    from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices

    rows = [
        {
            "kernel_turn_index": 1,
            "action_type": "read_page",
            "execution_state": "executed",
            "artifact_refs": [],
            "outputs_for_continuity": {
                "note": "visible text",
                "image_bytes": "AAAABBBBCCCC" * 200,
                "nested": {"image_base64": "ZZZ" * 200, "caption": "ok"},
            },
            "result_truncated": False,
        }
    ]
    slices = build_recent_tool_result_slices(rows)
    blob = json.dumps(slices[0]["outputs_excerpt"], ensure_ascii=False, default=str)
    assert "visible text" in blob
    assert "image_bytes" not in blob
    assert "image_base64" not in blob
    assert "AAAABBBB" not in blob
    assert "ZZZ" not in blob


def test_tool_result_slices_respect_max_records_and_chronology() -> None:
    from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices

    rows = [
        {
            "kernel_turn_index": i,
            "action_type": "noop",
            "execution_state": "executed",
            "artifact_refs": [],
            "outputs_for_continuity": {"turn": i},
            "result_truncated": False,
        }
        for i in (1, 2, 3, 4, 5)
    ]
    slices = build_recent_tool_result_slices(rows, max_records=3)
    assert [s["kernel_turn_index"] for s in slices] == [3, 4, 5]


def test_tool_result_slices_does_not_infer_semantic_conclusions() -> None:
    from harness.runtime.memory.tool_result_slices import build_recent_tool_result_slices

    rows = [
        {
            "kernel_turn_index": 1,
            "action_type": "hydrate_artifact_refs",
            "execution_state": "executed",
            "artifact_refs": ["artifact://a"],
            "outputs_for_continuity": {"result": "anything"},
            "result_truncated": False,
        }
    ]
    entry = build_recent_tool_result_slices(rows)[0]
    # No host-authored interpretation, ranking, relevance flag, or conclusion.
    for banned_key in (
        "relevance",
        "is_relevant",
        "conclusion",
        "summary",
        "verdict",
        "recommendation",
        "semantic_tag",
    ):
        assert banned_key not in entry


def test_state_repair_carries_slices_but_not_raw_step_record_arrays() -> None:
    """state_repair uses lean structured_state: slices are kept, raw step-record arrays are excluded."""
    doc = build_state_repair_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    structured = doc.prompt_body["structured_state"]
    # Slices are kept — they provide bounded mechanical context without the bulk.
    assert "recent_tool_result_slices" in structured
    # Raw step-record arrays are excluded from state_repair to keep closure-repair prompts lean.
    assert "recent_kernel_step_result_records" not in structured
    assert "recent_kernel_step_records" not in structured


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


def test_full_choose_action_prompt_includes_agent_requested_hydration_lane_when_pending() -> None:
    """When a pending hydrate_next record exists, the prompt structured_state surfaces it."""
    context = _context()
    context.loop_memory.continuity.pending_agent_hydration = {
        "source_turn_index": 2,
        "requested_refs": ["@result.revision_ref"],
        "resolved_refs": ["transcript_edit:working:rev:0001"],
        "reason": "inspect saved payload before publish",
        "errors": [],
        "hydrated_results": [{"ref_id": "transcript_edit:working:rev:0001", "kind": "stub", "payload": {}}],
        "hydration_errors": None,
        "status": "surfaced",
        "surfaced_iteration": 3,
    }

    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=context,
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )

    lane = doc.prompt_body["structured_state"].get("agent_requested_hydration")
    assert lane is not None
    assert lane["requested_refs"] == ["@result.revision_ref"]
    assert lane["resolved_refs"] == ["transcript_edit:working:rev:0001"]
    assert lane["reason"] == "inspect saved payload before publish"
    assert lane["hydrated_results"][0]["ref_id"] == "transcript_edit:working:rev:0001"


def test_full_choose_action_prompt_omits_lane_when_no_pending_record() -> None:
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    assert "agent_requested_hydration" not in doc.prompt_body.get("structured_state", {})


def test_full_choose_action_prompt_doctrine_mentions_hydrate_next() -> None:
    """The choose-action doctrine must surface the hydrate_next contract."""
    doc = build_choose_action_prompt_document(
        composed_input=_composed_input(),
        opaque_launch_context={"run_id": "r-1"},
        context=_context(),
        projection=_projection(),
        journal_verbatim_keep_n=2,
    )
    assert "hydrate_next" in doc.prompt_text
