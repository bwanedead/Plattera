from __future__ import annotations

import json

from harness.execution.session import ExecutionSessionManager
from harness.runtime.composition.contracts import ComposedTurnInput
from harness.runtime.memory import LoopMemoryState
from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.orchestration.contracts import OrchestratorContext, SharedStateProjection
from harness.runtime.orchestration.llm_prompt_builder import build_choose_action_prompt_document
from harness.runtime.orchestration.ref_window_projection import (
    build_hot_latest_ref_keys,
    collect_hot_refs_for_prompt,
    project_ref_list_for_prompt,
    project_refs_map_for_prompt,
)


def test_pinned_and_hydrate_refs_stay_exact() -> None:
    hot = collect_hot_refs_for_prompt(
        latest_refs={"final": "artifact://final", "stale": "image://old-1"},
        pinned_refs_projection={"active": [{"ref": "artifact://pinned"}]},
        agent_requested_hydration={
            "requested_refs": ["artifact://requested"],
            "resolved_refs": ["artifact://resolved"],
        },
    )
    assert "artifact://final" in hot
    assert "image://old-1" not in hot
    assert "artifact://pinned" in hot
    assert "artifact://requested" in hot
    assert "artifact://resolved" in hot

    windowed = project_refs_map_for_prompt(
        {
            "final": "artifact://final",
            "old_image_1": "image://old-1",
            "old_image_2": "image://old-2",
        },
        hot_refs=hot,
    )
    assert windowed["exact_refs"]["final"] == "artifact://final"
    assert windowed["summarized_refs"]["omitted_count"] == 2


def test_cold_evidence_refs_summarized_not_full_strings() -> None:
    refs = [f"image://old-{index}" for index in range(6)]
    windowed = project_ref_list_for_prompt(refs, hot_refs=frozenset())
    assert "evidence_refs" not in windowed or len(windowed.get("evidence_refs", [])) <= 2
    assert windowed["evidence_ref_count"] == 6
    assert windowed["evidence_refs_summarized"]["omitted_count"] == 6
    dumped = json.dumps(windowed)
    assert "image://old-3" not in dumped


def test_required_output_ref_key_stays_exact_in_latest_refs_projection() -> None:
    policy = {"required_output_ref_for_complete": "transcript_edit:output"}
    latest_refs = {
        "working": "artifact://working",
        "transcript_edit:output": "artifact://output-rev-0001",
        "transcript_edit:working:rev:0007": "artifact://working-rev-0007",
        "image://stale-1": "image://old-1",
    }
    hot_latest_ref_keys = build_hot_latest_ref_keys(
        domain_closure_policy=policy,
        latest_refs=latest_refs,
    )
    hot_refs = collect_hot_refs_for_prompt(
        latest_refs=latest_refs,
        hot_latest_ref_keys=hot_latest_ref_keys,
    )
    windowed = project_refs_map_for_prompt(
        latest_refs,
        hot_refs=hot_refs,
        hot_latest_ref_keys=hot_latest_ref_keys,
    )
    exact = windowed["exact_refs"]
    assert exact["working"] == "artifact://working"
    assert exact["transcript_edit:output"] == "artifact://output-rev-0001"
    assert exact["transcript_edit:working:rev:0007"] == "artifact://working-rev-0007"
    assert "image://stale-1" not in exact
    assert windowed["summarized_refs"]["omitted_count"] == 1


def test_choose_action_prompt_keeps_required_output_refs_exact_end_to_end() -> None:
    loop_memory = LoopMemoryState()
    loop_memory.continuity.latest_refs = {
        "transcript_edit:output": "artifact://output-rev-0001",
        "transcript_edit:working:rev:0007": "artifact://working-rev-0007",
        "image://stale-1": "image://old-1",
    }
    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-output-ref",
        loop_memory=loop_memory,
        request_id_prefix="req-output-ref",
    )
    latest_refs = dict(loop_memory.continuity.latest_refs)
    projection = SharedStateProjection(
        mission_state=new_mission_state(mission_id="m-out", loop_family="orchestration_kernel"),
        resolution_state=new_resolution_state(),
        latest_refs=latest_refs,
    )
    doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=()),
        opaque_launch_context={
            "domain_closure_policy": {
                "hard_enforced": True,
                "enforce_on_complete": True,
                "minimum_resolution_items_for_complete": 1,
                "required_output_ref_for_complete": "transcript_edit:output",
                "extra_policy_field_not_prompt_visible": True,
            }
        },
        context=context,
        projection=projection,
        journal_verbatim_keep_n=2,
    )
    projection_latest = doc.prompt_body["run_context"]["projection"]["latest_refs"]
    exact = projection_latest["exact_refs"]
    assert exact["transcript_edit:output"] == "artifact://output-rev-0001"
    assert exact["transcript_edit:working:rev:0007"] == "artifact://working-rev-0007"
    assert "image://stale-1" not in exact
    assert projection_latest["summarized_refs"]["omitted_count"] == 1
    visible_policy = doc.prompt_body["run_context"]["launch_context"]["domain_closure_policy"]
    assert visible_policy["required_output_ref_for_complete"] == "transcript_edit:output"
    assert "extra_policy_field_not_prompt_visible" not in visible_policy


def test_hot_evidence_refs_remain_exact() -> None:
    refs = ["artifact://hot", "image://cold"]
    windowed = project_ref_list_for_prompt(refs, hot_refs=frozenset({"artifact://hot"}))
    assert windowed["evidence_refs"] == ["artifact://hot"]
