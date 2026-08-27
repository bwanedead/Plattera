"""Tests for state_patch repair bundle carry-forward."""

from __future__ import annotations

from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.prompt_packet_builder import _compact_prompt_observability_summary
from harness.runtime.orchestration.state_patch_apply import (
    apply_state_patch,
    record_state_patch_no_patch_in_plan,
    row_skip_report_has_skips,
)
from harness.runtime.orchestration.state_patch_repair_bundle import (
    MAX_FRAGMENTS,
    REASON_TERMINAL_ROW_LIVE_WORK,
    build_state_patch_repair_bundle,
    build_terminal_row_consistency_repair_bundle,
    project_state_patch_repair_bundle_for_prompt,
)
from harness.runtime.orchestration.state_patch_repair_sanitization import (
    MAX_FRAGMENT_SERIALIZED_CHARS,
)


def _patch_with_bad_unit(*, unit_id: str = "parcel1_acreage", item_id: str = "visible_map_claims"):
    return {
        "resolution": {
            "items": [
                {
                    "item_id": item_id,
                    "title": "Visible map claims",
                    "kind": "claim_group",
                    "status": "open",
                    "covered_units": [
                        {
                            "unit_id": unit_id,
                            "title": "Parcel acreage",
                            "status": "closed",
                            "determined_value": "1.9 acres, more or less",
                            "evidence_refs": ["image:derived:abc"],
                            "reopen_triggers": 42,
                        }
                    ],
                }
            ]
        }
    }


def test_row_validation_failure_records_state_patch_repair_bundle() -> None:
    from harness.mission_state import new_mission_state, new_resolution_state

    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    rs = new_resolution_state()
    patch = _patch_with_bad_unit()
    _, _, skips = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert row_skip_report_has_skips(skips)
    bundle = build_state_patch_repair_bundle(
        state_patch=patch,
        row_skip_details={
            "resolution": {
                "items": [
                    {
                        "path": "resolution.items[visible_map_claims]",
                        "reason_code": "validation_failed",
                        "row_id": "visible_map_claims",
                        "validation_errors": [
                            "resolution.items[visible_map_claims].covered_units[parcel1_acreage].reopen_triggers: wrong type"
                        ],
                    }
                ]
            }
        },
    )
    assert bundle is not None
    assert bundle["reason"] == "state_patch_rows_skipped"
    assert bundle["fragments"]


def test_repair_bundle_preserves_atom_local_unit_flag_intent_despite_malformed_field() -> None:
    """Valid unit posture flags survive in the repair fragment when another field fails."""
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "visible_map_claims",
                    "title": "Visible map claims",
                    "kind": "claim_group",
                    "status": "open",
                    "covered_units": [
                        {
                            "unit_id": "parcel1_acreage",
                            "title": "Parcel acreage",
                            "requires_hitl": True,
                            "no_further_progress": True,
                            "reopen_triggers": 42,
                        }
                    ],
                }
            ]
        }
    }
    bundle = build_state_patch_repair_bundle(
        state_patch=patch,
        row_skip_details={
            "resolution": {
                "items": [
                    {
                        "path": "resolution.items[visible_map_claims]",
                        "reason_code": "validation_failed",
                        "row_id": "visible_map_claims",
                        "validation_errors": [
                            "resolution.items[visible_map_claims].covered_units[parcel1_acreage].reopen_triggers: wrong type"
                        ],
                    }
                ]
            }
        },
    )
    assert bundle is not None
    fragment = bundle["fragments"][0]["fragment"]
    assert fragment["unit_id"] == "parcel1_acreage"
    assert fragment["requires_hitl"] is True
    assert fragment["no_further_progress"] is True


def test_bundle_includes_rejected_patch_fragment_not_durable_state() -> None:
    from harness.mission_state import (
        ResolutionCoveredUnit,
        ResolutionItem,
        new_mission_state,
        new_resolution_state,
    )

    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    rs = new_resolution_state().model_copy(
        update={
            "items": [
                ResolutionItem(
                    item_id="visible_map_claims",
                    title="Visible map claims",
                    kind="claim_group",
                    status="open",
                    covered_units=[
                        ResolutionCoveredUnit(
                            unit_id="parcel1_acreage",
                            title="Parcel acreage",
                            status="open",
                        )
                    ],
                )
            ]
        }
    )
    patch = _patch_with_bad_unit()
    _, rs2, skips = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert rs2.items[0].covered_units[0].status == "open"
    assert row_skip_report_has_skips(skips)

    mem = LoopMemoryState()
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs2
    from harness.runtime.orchestration.contracts import ActionPlan
    from harness.runtime.orchestration.state_patch_apply import apply_action_plan_state_patch_to_loop_memory

    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=ActionPlan(state_patch=patch, rationale="t"),
        tracer=None,
        iteration=2,
        gate="test",
    )
    bundle = mem.continuity.state_patch_feedback.get("state_patch_repair_bundle") or {}
    fragment = bundle["fragments"][0]["fragment"]
    assert fragment["status"] == "closed"
    assert fragment["determined_value"] == "1.9 acres, more or less"
    assert mem.continuity.resolution_state.items[0].covered_units[0].status == "open"


def test_bundle_includes_validation_errors_and_path() -> None:
    patch = _patch_with_bad_unit(unit_id="parcel1_bearing_from_beginning")
    bundle = build_state_patch_repair_bundle(
        state_patch=patch,
        row_skip_details={
            "resolution": {
                "items": [
                    {
                        "path": "resolution.items[visible_map_claims]",
                        "reason_code": "validation_failed",
                        "row_id": "visible_map_claims",
                        "validation_errors": [
                            "resolution.items[visible_map_claims].covered_units[parcel1_bearing_from_beginning].reopen_triggers: Input should be a valid list"
                        ],
                    }
                ]
            }
        },
    )
    assert bundle is not None
    row = bundle["fragments"][0]
    assert "parcel1_bearing_from_beginning" in row["path"]
    assert row["validation_errors"]
    assert "reopen_triggers" in row["validation_errors"][0]


def test_bundle_truncates_large_fragments() -> None:
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "i1",
                    "title": "First",
                    "kind": "work_unit",
                    "status": "open",
                    "summary": "x" * 5000,
                    "notes": "y" * 5000,
                    "determined_value": "z" * 500,
                }
            ]
        }
    }
    bundle = build_state_patch_repair_bundle(
        state_patch=patch,
        row_skip_details={
            "resolution": {
                "items": [
                    {
                        "path": "resolution.items[i1]",
                        "reason_code": "validation_failed",
                        "row_id": "i1",
                        "validation_errors": ["resolution.items[i1].summary: string too long"],
                    }
                ]
            }
        },
    )
    assert bundle is not None
    row = bundle["fragments"][0]
    assert row.get("truncated") is True
    assert len(str(row["fragment"])) < MAX_FRAGMENT_SERIALIZED_CHARS + 200


def test_bundle_strips_heavy_fields_like_b64() -> None:
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "i1",
                    "title": "First",
                    "kind": "work_unit",
                    "status": "closed",
                    "determined_value": "value",
                    "b64": "AAAA",
                    "opaque_payload": {"bytes": b"raw"},
                }
            ]
        }
    }
    bundle = build_state_patch_repair_bundle(
        state_patch=patch,
        row_skip_details={
            "resolution": {
                "items": [
                    {
                        "path": "resolution.items[i1]",
                        "reason_code": "validation_failed",
                        "row_id": "i1",
                        "validation_errors": ["resolution.items[i1].title: required"],
                    }
                ]
            }
        },
    )
    fragment = bundle["fragments"][0]["fragment"]
    assert "b64" not in fragment
    assert "bytes" not in fragment.get("opaque_payload", {})


def test_bundle_is_prompt_visible_in_observability_summary() -> None:
    mem = LoopMemoryState()
    mem.continuity.state_patch_feedback = {
        "outcome": "applied",
        "iteration": 2,
        "state_patch_repair_bundle": {
            "schema_version": 1,
            "reason": "state_patch_rows_skipped",
            "instruction": "Repair the rejected patch shape/content directly.",
            "fragments": [
                {
                    "path": "resolution.items[i1]",
                    "reason_code": "validation_failed",
                    "validation_errors": ["bad field"],
                    "fragment": {"item_id": "i1", "status": "closed"},
                }
            ],
        },
    }
    summary = build_prompt_observability_summary(mem)
    assert "state_patch_repair_bundle" in summary
    assert summary["state_patch_repair_bundle"]["prompt_instruction"]
    compact = _compact_prompt_observability_summary(summary)
    assert "state_patch_repair_bundle" in compact


def test_clean_later_patch_clears_prior_repair_bundle() -> None:
    from harness.mission_state import new_mission_state, new_resolution_state
    from harness.runtime.orchestration.contracts import ActionPlan
    from harness.runtime.orchestration.state_patch_apply import apply_action_plan_state_patch_to_loop_memory

    mem = LoopMemoryState()
    mem.continuity.mission_state = new_mission_state(mission_id="m1", loop_family="orchestration_kernel")
    mem.continuity.resolution_state = new_resolution_state()
    bad = _patch_with_bad_unit()
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=ActionPlan(state_patch=bad, rationale="bad"),
        tracer=None,
        iteration=1,
        gate="test",
    )
    assert mem.continuity.state_patch_feedback.get("state_patch_repair_bundle")

    good = {
        "resolution": {
            "items": [
                {
                    "item_id": "visible_map_claims",
                    "title": "Visible map claims",
                    "kind": "claim_group",
                    "status": "open",
                    "covered_units": [
                        {
                            "unit_id": "parcel1_acreage",
                            "title": "Parcel acreage",
                            "status": "closed",
                            "determined_value": "1.9 acres, more or less",
                            "evidence_refs": ["image:derived:abc"],
                            "reopen_triggers": ["Reopen if needed."],
                        }
                    ],
                }
            ]
        }
    }
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=ActionPlan(state_patch=good, rationale="good"),
        tracer=None,
        iteration=2,
        gate="test",
    )
    fb = mem.continuity.state_patch_feedback
    assert fb["outcome"] == "applied"
    assert "state_patch_repair_bundle" not in fb


def test_new_row_skip_replaces_prior_repair_bundle() -> None:
    from harness.runtime.orchestration.contracts import ActionPlan
    from harness.runtime.orchestration.state_patch_apply import apply_action_plan_state_patch_to_loop_memory

    mem = LoopMemoryState()
    patch1 = _patch_with_bad_unit(unit_id="u1")
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=ActionPlan(state_patch=patch1, rationale="bad1"),
        tracer=None,
        iteration=1,
        gate="test",
    )
    first_path = mem.continuity.state_patch_feedback["state_patch_repair_bundle"]["fragments"][0]["path"]

    patch2 = _patch_with_bad_unit(unit_id="u2", item_id="other_item")
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=ActionPlan(state_patch=patch2, rationale="bad2"),
        tracer=None,
        iteration=2,
        gate="test",
    )
    second_path = mem.continuity.state_patch_feedback["state_patch_repair_bundle"]["fragments"][0]["path"]
    assert first_path != second_path
    assert "u2" in second_path or "other_item" in second_path


def test_no_patch_preserves_existing_repair_bundle() -> None:
    mem = LoopMemoryState()
    bundle = {
        "schema_version": 1,
        "reason": "state_patch_rows_skipped",
        "instruction": "Repair",
        "fragments": [{"path": "resolution.items[i1]", "fragment": {"item_id": "i1"}}],
    }
    mem.continuity.state_patch_feedback = {
        "outcome": "applied",
        "iteration": 1,
        "state_patch_repair_bundle": bundle,
        "semantic_repair_debt": ["determined_value"],
    }
    record_state_patch_no_patch_in_plan(loop_memory=mem, tracer=None, iteration=2)
    fb = mem.continuity.state_patch_feedback
    assert fb["outcome"] == "no_patch"
    assert fb["state_patch_repair_bundle"]["fragments"][0]["path"] == "resolution.items[i1]"


def test_project_for_prompt_includes_instruction() -> None:
    projected = project_state_patch_repair_bundle_for_prompt(
        {
            "state_patch_repair_bundle": {
                "fragments": [{"path": "resolution.items[i1]", "fragment": {"item_id": "i1"}}]
            }
        }
    )
    assert projected is not None
    assert "Prior state_patch integration failed" in projected["prompt_instruction"]


def test_bundle_fragment_cap_limits_fragments() -> None:
    details = {
        "resolution": {
            "items": [
                {
                    "path": f"resolution.items[i{index}]",
                    "reason_code": "validation_failed",
                    "row_id": f"i{index}",
                    "validation_errors": ["bad"],
                }
                for index in range(MAX_FRAGMENTS + 3)
            ]
        }
    }
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": f"i{index}",
                    "title": f"Item {index}",
                    "kind": "work_unit",
                    "status": "open",
                    "reopen_triggers": 1,
                }
                for index in range(MAX_FRAGMENTS + 3)
            ]
        }
    }
    bundle = build_state_patch_repair_bundle(state_patch=patch, row_skip_details=details)
    assert bundle is not None
    assert len(bundle["fragments"]) == MAX_FRAGMENTS


def test_bundle_handles_single_item_mapping_patch_shape() -> None:
    patch = {
        "resolution": {
            "items": {
                "item_id": "i1",
                "title": "Item",
                "kind": "work_unit",
                "status": "closed",
                "determined_value": "value",
            }
        }
    }
    details = {
        "resolution": {
            "items": [
                {
                    "path": "resolution.items[i1]",
                    "reason_code": "validation_failed",
                    "row_id": "i1",
                    "validation_errors": ["resolution.items[i1].status: bad"],
                }
            ]
        }
    }

    bundle = build_state_patch_repair_bundle(state_patch=patch, row_skip_details=details)
    assert bundle is not None
    assert bundle["fragments"][0]["fragment"]["determined_value"] == "value"


def test_terminal_row_consistency_repair_bundle_wire_shape() -> None:
    from harness.mission_state import (
        REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        TerminalRowConflict,
        TerminalRowConsistencyResult,
    )

    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "item-1",
                    "status": "closed",
                    "covered_units": [{"unit_id": "u1", "status": "closed"}],
                }
            ]
        }
    }
    result = TerminalRowConsistencyResult(
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        conflicts=(
            TerminalRowConflict(
                coordinate="resolution.items[item-1].covered_units[u1]",
                fields=("next_needed_step",),
            ),
        ),
        conflicts_omitted_count=0,
    )
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    assert bundle["schema_version"] == 1
    assert bundle["reason"] == REASON_TERMINAL_ROW_LIVE_WORK
    frag = bundle["fragments"][0]
    assert frag["path"] == "resolution.items[item-1].covered_units[u1]"
    assert frag["conflicting_fields"] == ["next_needed_step"]
    assert frag["required_clear_delta"] == {"next_needed_step": None}
    assert frag["fragment"]["unit_id"] == "u1"
    assert frag["fragment"]["status"] == "closed"
