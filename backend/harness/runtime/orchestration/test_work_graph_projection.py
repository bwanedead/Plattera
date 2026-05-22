from __future__ import annotations

import copy
import json

from harness.execution.session import ExecutionSessionManager
from harness.mission_state import (
    ResolutionCoveredUnit,
    ResolutionItem,
    new_mission_state,
    new_resolution_state,
)
from harness.runtime.composition.contracts import ComposedTurnInput
from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.runtime.orchestration.work_graph_projection import build_prompt_work_graph_projection


LONG_NOTEBOOK_PROSE = (
    "This is a long notebook-style paragraph with many details that may be useful in durable audit state, "
    "but it should not stay hot in the prompt once the item is closed. "
) * 2
LONG_VERIFICATION_TEXT_SHOULD_NOT_BE_HOT = "LONG_VERIFICATION_TEXT_SHOULD_NOT_BE_HOT " * 40
LONG_COVERED_UNIT_NOTE_SHOULD_NOT_BE_HOT = "LONG_COVERED_UNIT_NOTE_SHOULD_NOT_BE_HOT " * 40


def test_closed_item_projects_compactly_and_omits_long_prose() -> None:
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "closed-a",
                "title": "Closed value",
                "kind": "claim",
                "status": "closed",
                "determination": "earned",
                "label": "Closed value",
                "value_kind": "identifier",
                "candidate_values": ["A", "B"],
                "determined_value": "A",
                "summary": LONG_NOTEBOOK_PROSE,
                "notes": LONG_NOTEBOOK_PROSE,
                "verification_basis": LONG_NOTEBOOK_PROSE,
                "closure_summary": "Verified by direct evidence.",
                "reopen_triggers": ["conflicting source appears"],
                "evidence_refs": ["artifact://evidence-a"],
                "evidence_locators": [
                    {"ref_id": "artifact://evidence-a", "locator_kind": "text_span", "line_start": 2}
                ],
                "covered_units": [
                    {
                        "unit_id": "closed-a-value",
                        "title": "Closed value atom",
                        "status": "closed",
                        "determination": "earned",
                        "candidate_values": ["A", "B"],
                        "determined_value": "A",
                        "verification_basis": LONG_NOTEBOOK_PROSE,
                        "closure_summary": "A was verified.",
                        "reopen_triggers": ["new authoritative value"],
                        "evidence_refs": ["artifact://evidence-a"],
                        "evidence_locators": [
                            {"ref_id": "artifact://evidence-a", "locator_kind": "text_span", "line_start": 2}
                        ],
                    },
                    {
                        "unit_id": "closed-a-open-subunit",
                        "title": "Open sub-unit under closed parent",
                        "status": "open",
                        "summary": "This sub-unit still needs work.",
                        "next_needed_step": "Reopen parent or resolve this sub-unit.",
                    },
                ],
            }
        ]
    )

    projection = build_prompt_work_graph_projection(resolution)
    item = projection["items"][0]
    unit = item["covered_units"][0]
    open_unit = item["covered_units"][1]

    assert item["item_id"] == "closed-a"
    assert "id" not in item
    assert item["label"] == "Closed value"
    assert item["value_kind"] == "identifier"
    assert "candidate_values" not in item
    assert item["determined_value"] == "A"
    assert "closure_summary" not in item
    assert item["reopen_triggers"] == ["conflicting source appears"]
    assert item["evidence_ref_count"] == 1
    assert item["evidence_locator_count"] == 1
    assert "summary" not in item
    assert "notes" not in item
    assert "verification_basis" not in item
    assert "candidate_values" not in unit
    assert unit["determined_value"] == "A"
    assert unit["unit_id"] == "closed-a-value"
    assert "id" not in unit
    assert "closure_summary" not in unit
    assert unit["evidence_ref_count"] == 1
    assert unit["evidence_locator_count"] == 1
    assert open_unit["unit_id"] == "closed-a-open-subunit"
    assert open_unit["summary"] == "This sub-unit still needs work."
    assert open_unit["next_needed_step"] == "Reopen parent or resolve this sub-unit."
    assert LONG_NOTEBOOK_PROSE not in json.dumps(projection)


def test_active_and_open_items_keep_needed_detail() -> None:
    resolution = new_resolution_state(
        active_item_id="open-a",
        items=[
            {
                "item_id": "open-a",
                "title": "Open value",
                "kind": "claim",
                "status": "open",
                "summary": "Need to inspect candidate records.",
                "verification_basis": "Initial pass found two plausible values.",
                "next_needed_step": "Hydrate the focused evidence artifact.",
                "notes": "Keep both candidates visible until direct evidence resolves them.",
                "completion_criteria": "One candidate is earned or the item is blocked.",
                "covered_units": [
                    {
                        "unit_id": "open-a-value",
                        "title": "Open value atom",
                        "status": "open",
                        "candidate_values": ["alpha", "beta"],
                        "next_needed_step": "Compare alpha and beta against evidence.",
                    },
                    {
                        "unit_id": "open-a-closed-value",
                        "title": "Closed value atom under active item",
                        "status": "closed",
                        "verification_basis": LONG_NOTEBOOK_PROSE,
                        "determined_value": "gamma",
                    },
                ],
            }
        ],
    )

    item = build_prompt_work_graph_projection(resolution)["items"][0]
    unit = item["covered_units"][0]
    closed_unit = item["covered_units"][1]
    assert item["summary"] == "Need to inspect candidate records."
    assert item["verification_basis"] == "Initial pass found two plausible values."
    assert item["next_needed_step"] == "Hydrate the focused evidence artifact."
    assert item["notes"] == "Keep both candidates visible until direct evidence resolves them."
    assert item["completion_criteria"] == "One candidate is earned or the item is blocked."
    assert unit["candidate_values"] == ["alpha", "beta"]
    assert unit["next_needed_step"] == "Compare alpha and beta against evidence."
    assert closed_unit["determined_value"] == "gamma"
    assert "verification_basis" not in closed_unit


def test_blocked_item_keeps_blocker_and_next_step_detail() -> None:
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "blocked-a",
                "title": "Blocked decision",
                "kind": "decision",
                "status": "blocked",
                "blocking": True,
                "requires_hitl": True,
                "no_further_progress": True,
                "dependencies": ["input-a"],
                "verification_basis": "Available evidence cannot distinguish options.",
                "next_needed_step": "Ask the operator which option governs.",
            }
        ]
    )

    item = build_prompt_work_graph_projection(resolution)["items"][0]
    assert item["blocking"] is True
    assert item["requires_hitl"] is True
    assert item["no_further_progress"] is True
    assert item["dependencies"] == ["input-a"]
    assert item["verification_basis"] == "Available evidence cannot distinguish options."
    assert item["next_needed_step"] == "Ask the operator which option governs."


def test_semantic_repair_debt_keeps_repair_feedback_visible() -> None:
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "open-a",
                "title": "Open value",
                "kind": "claim",
                "status": "open",
            }
        ]
    )
    feedback = {
        "outcome": "not_applied",
        "reason_code": "items_validation_failed",
        "semantic_repair_debt": ["determined_value", "evidence_refs"],
        "row_skip_details": {"resolution": {"items": [{"path": "resolution.items[open-a]"}]}},
        "repair_targets": ["fix_covered_unit_value"],
    }

    projection = build_prompt_work_graph_projection(resolution, state_patch_feedback=feedback)
    assert projection["repair_feedback"]["outcome"] == "not_applied"
    assert projection["repair_feedback"]["semantic_repair_debt"] == ["determined_value", "evidence_refs"]
    assert projection["repair_feedback"]["repair_targets"] == ["fix_covered_unit_value"]
    assert "row_skip_details" in projection["repair_feedback"]


def test_projection_does_not_mutate_full_durable_state() -> None:
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "closed-a",
                "title": "Closed value",
                "kind": "claim",
                "status": "closed",
                "summary": LONG_NOTEBOOK_PROSE,
                "notes": LONG_NOTEBOOK_PROSE,
            }
        ],
        opaque_payload={"launch_context": {"hidden": True}, "retained": "durable"},
    )
    before = resolution.model_dump(mode="json")
    before_deepcopy = copy.deepcopy(before)

    projection = build_prompt_work_graph_projection(resolution)

    assert resolution.model_dump(mode="json") == before_deepcopy
    assert before["items"][0]["summary"] == LONG_NOTEBOOK_PROSE
    assert projection["items"][0]["item_id"] == "closed-a"
    assert projection["opaque_payload_keys"] == ["retained"]


def test_schema_accepts_optional_closure_summary_and_reopen_triggers() -> None:
    item = ResolutionItem(
        item_id="i1",
        title="Compact closed item",
        kind="claim",
        status="closed",
        closure_summary="Closed after direct verification.",
        reopen_triggers=["new source", "operator correction"],
    )
    unit = ResolutionCoveredUnit(
        unit_id="u1",
        title="Compact closed unit",
        closure_summary="Value verified.",
        reopen_triggers=["conflicting record"],
    )
    omitted = ResolutionItem(item_id="i2", title="No closure memory yet", kind="claim", status="open")

    assert item.closure_summary == "Closed after direct verification."
    assert item.reopen_triggers == ["new source", "operator correction"]
    assert unit.closure_summary == "Value verified."
    assert unit.reopen_triggers == ["conflicting record"]
    assert omitted.closure_summary is None
    assert omitted.reopen_triggers == []


def test_prompt_packet_includes_compact_projection_in_run_context() -> None:
    loop_memory = LoopMemoryState()
    loop_memory.continuity.state_patch_feedback = {
        "outcome": "not_applied",
        "semantic_repair_debt": ["evidence_refs"],
    }
    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess",
        loop_memory=loop_memory,
        request_id_prefix="req",
    )
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "closed-a",
                "title": "Closed value",
                "kind": "claim",
                "status": "closed",
                "summary": LONG_NOTEBOOK_PROSE,
                "covered_units": [
                    {
                        "unit_id": "closed-a-value",
                        "title": "Closed value atom",
                        "status": "closed",
                        "candidate_values": ["A", "B"],
                        "determined_value": "B",
                        "evidence_refs": ["artifact://evidence"],
                    }
                ],
            }
        ]
    )
    mission = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        resolution_state=resolution,
    )
    doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=()),
        opaque_launch_context={},
        context=context,
        projection=SharedStateProjection(
            mission_state=mission,
            resolution_state=resolution,
            latest_refs={"final": "artifact://final"},
        ),
        journal_verbatim_keep_n=2,
    )

    projected_resolution = doc.prompt_body["run_context"]["projection"]["resolution_state"]
    assert projected_resolution["projection_kind"] == "work_graph_projection.v1"
    assert projected_resolution["items"][0]["item_id"] == "closed-a"
    assert "id" not in projected_resolution["items"][0]
    assert projected_resolution["items"][0]["covered_units"][0]["determined_value"] == "B"
    assert projected_resolution["repair_feedback"]["semantic_repair_debt"] == ["evidence_refs"]
    assert "summary" not in projected_resolution["items"][0]
    assert LONG_NOTEBOOK_PROSE not in doc.prompt_text


def test_closed_rows_drop_sentinel_graph_text() -> None:
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "closed-sentinel",
                "title": "Closed sentinel row",
                "kind": "group",
                "status": "closed",
                "structure_kind": "group",
                "determined_value": "group-value",
                "verification_basis": LONG_VERIFICATION_TEXT_SHOULD_NOT_BE_HOT,
                "notes": LONG_COVERED_UNIT_NOTE_SHOULD_NOT_BE_HOT,
                "closure_summary": LONG_NOTEBOOK_PROSE,
                "covered_units": [
                    {
                        "unit_id": "closed-sentinel-unit",
                        "title": "Closed covered unit",
                        "status": "closed",
                        "determined_value": "unit-value",
                        "verification_basis": LONG_VERIFICATION_TEXT_SHOULD_NOT_BE_HOT,
                        "notes": LONG_COVERED_UNIT_NOTE_SHOULD_NOT_BE_HOT,
                        "candidate_values": ["old-a", "old-b"],
                    }
                ],
            }
        ]
    )
    projection = build_prompt_work_graph_projection(resolution)
    dumped = json.dumps(projection)
    assert LONG_VERIFICATION_TEXT_SHOULD_NOT_BE_HOT not in dumped
    assert LONG_COVERED_UNIT_NOTE_SHOULD_NOT_BE_HOT not in dumped
    assert LONG_NOTEBOOK_PROSE not in dumped


def test_hot_refs_keep_closed_evidence_exact() -> None:
    resolution = new_resolution_state(
        items=[
            {
                "item_id": "closed-hot-evidence",
                "title": "Closed with hot evidence",
                "kind": "claim",
                "status": "closed",
                "determined_value": "X",
                "evidence_refs": ["artifact://hot-evidence"],
            }
        ]
    )
    projection = build_prompt_work_graph_projection(
        resolution,
        hot_refs=frozenset({"artifact://hot-evidence"}),
    )
    item = projection["items"][0]
    assert item["evidence_refs"] == ["artifact://hot-evidence"]
