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


def _window_with_policy(
    latest_refs: dict[str, object],
    *,
    required_output: str = "transcript_edit:output",
) -> dict[str, object]:
    policy = {"required_output_ref_for_complete": required_output}
    hot_latest_ref_keys = build_hot_latest_ref_keys(
        domain_closure_policy=policy,
        latest_refs=latest_refs,
    )
    hot_refs = collect_hot_refs_for_prompt(
        latest_refs=latest_refs,
        hot_latest_ref_keys=hot_latest_ref_keys,
    )
    return project_refs_map_for_prompt(
        latest_refs,
        hot_refs=hot_refs,
        hot_latest_ref_keys=hot_latest_ref_keys,
    )


def test_unqualified_aggregate_working_ref_stays_exact() -> None:
    windowed = _window_with_policy(
        {
            "transcript_edit:working": "artifact://working-head",
            "image://cold": "image://old-1",
        }
    )
    assert windowed["exact_refs"]["transcript_edit:working"] == "artifact://working-head"
    assert "image://cold" not in windowed["exact_refs"]


def test_unqualified_exact_revision_stays_exact() -> None:
    windowed = _window_with_policy(
        {
            "transcript_edit:working:rev:0001": "artifact://working-rev-0001",
            "image://cold": "image://old-1",
        }
    )
    assert (
        windowed["exact_refs"]["transcript_edit:working:rev:0001"]
        == "artifact://working-rev-0001"
    )


def test_dossier_qualified_aggregate_working_ref_stays_exact() -> None:
    key = "892abc34:transcript_edit:working"
    windowed = _window_with_policy(
        {
            key: "artifact://dossier-working-head",
            "image://cold": "image://old-1",
        }
    )
    assert windowed["exact_refs"][key] == "artifact://dossier-working-head"


def test_dossier_qualified_exact_revision_stays_exact() -> None:
    key = "892abc34:transcript_edit:working:rev:0001"
    windowed = _window_with_policy(
        {
            key: "artifact://dossier-working-rev",
            "image://cold": "image://old-1",
        }
    )
    assert windowed["exact_refs"][key] == "artifact://dossier-working-rev"


def test_working_tier_matches_key_or_normalized_value() -> None:
    by_key = _window_with_policy(
        {
            "892abc34:transcript_edit:working:rev:0002": "artifact://opaque-value",
            "noise": "image://cold",
        }
    )
    assert "892abc34:transcript_edit:working:rev:0002" in by_key["exact_refs"]

    by_value = _window_with_policy(
        {
            "alias_working_head": "892abc34:transcript_edit:working",
            "alias_working_rev": {
                "ref": "892abc34:transcript_edit:working:rev:0003",
            },
            "noise": "image://cold",
        }
    )
    exact = by_value["exact_refs"]
    assert exact["alias_working_head"] == "892abc34:transcript_edit:working"
    assert exact["alias_working_rev"] == "892abc34:transcript_edit:working:rev:0003"
    assert "noise" not in exact


def test_similar_prefixes_and_suffixes_do_not_match() -> None:
    latest_refs = {
        "nottranscript_edit:working": "artifact://false-prefix",
        "transcript_edit:workingish": "artifact://false-suffix",
        "wrapper:nottranscript_edit:working": "artifact://false-wrapped",
        "wrapper:transcript_edit:workingish": "artifact://false-wrapped-suffix",
        "image://cold": "image://old-1",
    }
    windowed = _window_with_policy(latest_refs)
    exact = windowed.get("exact_refs") or {}
    for key in (
        "nottranscript_edit:working",
        "transcript_edit:workingish",
        "wrapper:nottranscript_edit:working",
        "wrapper:transcript_edit:workingish",
        "image://cold",
    ):
        assert key not in exact
    assert windowed["summarized_refs"]["omitted_count"] == 5


def test_other_output_family_working_ref_stays_cold() -> None:
    windowed = _window_with_policy(
        {
            "deed_to_ir:working": "artifact://deed-working",
            "892abc34:deed_to_ir:working:rev:0001": "artifact://deed-rev",
            "transcript_edit:working": "artifact://te-working",
        },
        required_output="transcript_edit:output",
    )
    exact = windowed["exact_refs"]
    assert exact["transcript_edit:working"] == "artifact://te-working"
    assert "deed_to_ir:working" not in exact
    assert "892abc34:deed_to_ir:working:rev:0001" not in exact


def test_derived_image_tails_remain_summarized() -> None:
    dossier = "892abc34-ed4d-4e85-a0cb-9a5ddc133f31"
    latest_refs = {
        f"{dossier}:transcript_edit:working": f"{dossier}:transcript_edit:working",
        f"{dossier}:transcript_edit:working:rev:0001": (
            f"{dossier}:transcript_edit:working:rev:0001"
        ),
        **{
            f"image://derived-{index}": f"image://derived-{index}"
            for index in range(8)
        },
    }
    windowed = _window_with_policy(latest_refs)
    exact = windowed["exact_refs"]
    assert f"{dossier}:transcript_edit:working" in exact
    assert f"{dossier}:transcript_edit:working:rev:0001" in exact
    assert all(not key.startswith("image://") for key in exact)
    assert windowed["summarized_refs"]["omitted_count"] == 8
    assert windowed["summarized_refs"]["counts_by_kind"]["image"] == 8


def test_production_shaped_pressure_keeps_qualified_working_heads_exact() -> None:
    dossier = "892abc34-ed4d-4e85-a0cb-9a5ddc133f31"
    working_agg = f"{dossier}:transcript_edit:working"
    working_rev = f"{dossier}:transcript_edit:working:rev:0001"
    latest_refs = {
        working_agg: working_agg,
        working_rev: working_rev,
        "transcript_edit:output": "artifact://output-head",
        **{
            f"{dossier}:derived_images:{index:02d}": f"image://crop-{index}"
            for index in range(12)
        },
        "noise_other": "artifact://unrelated",
    }
    windowed = _window_with_policy(
        latest_refs,
        required_output="transcript_edit:output",
    )
    exact = windowed["exact_refs"]
    assert exact[working_agg] == working_agg
    assert exact[working_rev] == working_rev
    assert exact["transcript_edit:output"] == "artifact://output-head"
    assert "noise_other" not in exact
    assert all(":derived_images:" not in key for key in exact)
    assert windowed["summarized_refs"]["omitted_count"] == 13


def test_choose_action_prompt_keeps_qualified_working_heads_exact_after_delivery_expires() -> None:
    from harness.runtime.orchestration.llm_prompt_builder import build_state_repair_prompt_document
    from harness.runtime.orchestration.prompt_budget import build_prompt_budget_report

    dossier = "892abc34-ed4d-4e85-a0cb-9a5ddc133f31"
    working_agg = f"{dossier}:transcript_edit:working"
    working_rev = f"{dossier}:transcript_edit:working:rev:0001"
    loop_memory = LoopMemoryState()
    loop_memory.iterations = 12
    loop_memory.continuity.latest_refs = {
        working_agg: working_agg,
        working_rev: working_rev,
        **{f"image://stale-{index}": f"image://stale-{index}" for index in range(6)},
    }
    assert not loop_memory.continuity.pending_result_deliveries

    context = OrchestratorContext(
        session_manager=ExecutionSessionManager(),
        session_id="sess-br036",
        loop_memory=loop_memory,
        request_id_prefix="req-br036",
    )
    projection = SharedStateProjection(
        mission_state=new_mission_state(mission_id="m-br036", loop_family="orchestration_kernel"),
        resolution_state=new_resolution_state(),
        latest_refs=dict(loop_memory.continuity.latest_refs),
    )
    launch = {
        "domain_closure_policy": {
            "required_output_ref_for_complete": "transcript_edit:output",
        }
    }
    choose_doc = build_choose_action_prompt_document(
        composed_input=ComposedTurnInput(blocks=()),
        opaque_launch_context=launch,
        context=context,
        projection=projection,
        journal_verbatim_keep_n=2,
    )
    structured = choose_doc.prompt_body.get("structured_state") or {}
    assert "latest_action_results" not in structured
    # full_choose_action drops duplicate top-level latest_refs; projection is canonical.
    assert "latest_refs" not in choose_doc.prompt_body["run_context"]
    projection_exact = choose_doc.prompt_body["run_context"]["projection"]["latest_refs"][
        "exact_refs"
    ]
    assert projection_exact[working_agg] == working_agg
    assert projection_exact[working_rev] == working_rev
    assert all(not key.startswith("image://") for key in projection_exact)

    repair_doc = build_state_repair_prompt_document(
        composed_input=ComposedTurnInput(blocks=()),
        opaque_launch_context=launch,
        context=context,
        projection=projection,
        journal_verbatim_keep_n=2,
    )
    top_exact = repair_doc.prompt_body["run_context"]["latest_refs"]["exact_refs"]
    repair_projection_exact = repair_doc.prompt_body["run_context"]["projection"]["latest_refs"][
        "exact_refs"
    ]
    for exact in (top_exact, repair_projection_exact):
        assert exact[working_agg] == working_agg
        assert exact[working_rev] == working_rev
        assert all(not key.startswith("image://") for key in exact)

    assert choose_doc.prompt_budget is not None
    recomputed = build_prompt_budget_report(
        instruction_text=choose_doc.instruction_text,
        prompt_body=choose_doc.prompt_body,
    )
    assert recomputed["buckets"]["total_prompt_chars"] == choose_doc.prompt_budget["buckets"][
        "total_prompt_chars"
    ]
    assert recomputed["buckets"]["latest_refs"] == choose_doc.prompt_budget["buckets"][
        "latest_refs"
    ]

def test_working_tier_match_rejects_non_string_tokens() -> None:
    class _LooksLikeWorking:
        def __str__(self) -> str:
            return "transcript_edit:working"

    latest_refs = {
        "opaque": _LooksLikeWorking(),
        "truth": "transcript_edit:working",
    }
    hot_keys = build_hot_latest_ref_keys(
        domain_closure_policy={"required_output_ref_for_complete": "transcript_edit:output"},
        latest_refs=latest_refs,
    )
    assert "truth" in hot_keys
    assert "opaque" not in hot_keys
