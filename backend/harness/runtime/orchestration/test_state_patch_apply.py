"""Tests for generic model-authored ``state_patch`` merge (no semantic inference)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from harness.mission_state import new_mission_state, new_resolution_state
from harness.runtime.orchestration import state_patch_apply as state_patch_apply_mod
from harness.runtime.orchestration.state_patch_apply import (
    StatePatchError,
    apply_state_patch,
)


def _base_states():
    ms = new_mission_state(mission_id="m1", loop_family="orchestration_kernel", objective="prior")
    rs = new_resolution_state()
    return ms, rs


def test_apply_patch_rejects_unknown_top_level_key() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(mission_state=ms, resolution_state=rs, state_patch={"transcript_edit": {}})
    assert excinfo.value.reason_code == "state_patch_unknown_keys"


def test_apply_patch_rejects_unknown_resolution_key() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"resolution": {"items": [], "extra": 1}},
        )
    assert excinfo.value.reason_code == "resolution_unknown_keys"


def test_item_upsert_and_active_item_persist() -> None:
    ms, rs = _base_states()
    item = {
        "item_id": "i1",
        "title": "First",
        "kind": "work_unit",
        "status": "open",
    }
    ms2, rs2, _sk0 = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"resolution": {"items": [item], "active_item_id": "i1"}},
    )
    assert len(rs2.items) == 1
    assert rs2.items[0].status == "open"
    assert rs2.active_item_id == "i1"
    assert ms2.resolution_state is rs2

    ms3, rs3, _sk1 = apply_state_patch(
        mission_state=ms2,
        resolution_state=rs2,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "status": "closed",
                    }
                ],
            }
        },
    )
    assert len(rs3.items) == 1
    assert rs3.items[0].status == "closed"
    assert rs3.items[0].title == "First"
    assert rs3.active_item_id == "i1"


def test_item_partial_update_preserves_evidence_refs() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "title": "First",
                        "kind": "work_unit",
                        "status": "open",
                        "evidence_refs": ["artifact://a", "artifact://b"],
                    }
                ],
            }
        },
    )
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={"resolution": {"items": [{"item_id": "i1", "status": "closed"}]}},
    )
    assert rs3.items[0].evidence_refs == ["artifact://a", "artifact://b"]
    assert rs3.items[0].status == "closed"


def test_item_partial_update_preserves_determination() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "title": "First",
                        "kind": "work_unit",
                        "status": "in_review",
                        "determination": "provisional",
                        "verification_basis": "Compared the claim against source evidence.",
                        "completion_criteria": "Resolve the discrepancy against the strongest available evidence.",
                    }
                ],
            }
        },
    )
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={"resolution": {"items": [{"item_id": "i1", "status": "closed"}]}},
    )
    assert rs3.items[0].determination == "provisional"
    assert rs3.items[0].verification_basis == "Compared the claim against source evidence."
    assert (
        rs3.items[0].completion_criteria
        == "Resolve the discrepancy against the strongest available evidence."
    )
    assert rs3.items[0].status == "closed"


def test_item_partial_update_preserves_structure_kind() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "i-group",
                        "title": "Grouped claim",
                        "kind": "claim_group",
                        "status": "open",
                        "structure_kind": "group",
                    }
                ],
            }
        },
    )
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={"resolution": {"items": [{"item_id": "i-group", "status": "in_review"}]}},
    )
    assert rs3.items[0].status == "in_review"
    assert rs3.items[0].structure_kind == "group"


def test_mission_objective_shallow_summary_merge() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(update={"blocker_summary": {"a": 1}})
    ms2, rs2, skips_m = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"blocker_summary": {"b": 2}, "objective": "next"}},
    )
    assert skips_m["resolution"]["items"] == {}
    assert skips_m["resolution"]["relations"] == {}
    assert ms2.objective == "next"
    assert ms2.blocker_summary == {"a": 1, "b": 2}
    assert rs2 is rs


def test_mission_success_conditions_merge_by_condition_id() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "success_conditions": [
                    {
                        "condition_id": "source-grounded-transcript",
                        "title": "Source-grounded transcript exists",
                        "status": "open",
                        "determination": "provisional",
                        "completion_criteria": "All visible operative source text is reviewed and reconciled.",
                    }
                ]
            }
        },
    )
    ms3, _, _ = apply_state_patch(
        mission_state=ms2,
        resolution_state=rs,
        state_patch={
            "mission": {
                "success_conditions": [
                    {
                        "condition_id": "source-grounded-transcript",
                        "status": "in_review",
                        "verification_basis": "Compared the transcript against the source image and peer drafts.",
                    }
                ]
            }
        },
    )
    assert len(ms3.success_conditions) == 1
    condition = ms3.success_conditions[0]
    assert condition.status == "in_review"
    assert condition.determination == "provisional"
    assert condition.completion_criteria == "All visible operative source text is reviewed and reconciled."
    assert condition.verification_basis == "Compared the transcript against the source image and peer drafts."


def test_mission_patch_rejects_host_owned_telemetry_keys() -> None:
    ms, rs = _base_states()
    for forbidden in (
        "latest_refs_summary",
        "terminal_summary",
        "prompt_observability_summary",
    ):
        with pytest.raises(StatePatchError) as excinfo:
            apply_state_patch(
                mission_state=ms,
                resolution_state=rs,
                state_patch={"mission": {forbidden: {}}},
            )
        assert excinfo.value.reason_code == "mission_unknown_keys"


def test_mission_patch_accepts_closure_state_and_merges_dimensions() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "closure_state": {
                    "overall_status": "open",
                    "summary": "Closure still in progress",
                    "ready_to_publish": False,
                    "ready_to_close": False,
                    "dimensions": [
                        {
                            "dimension_id": "layer_1_delta_convergence",
                            "title": "Layer 1",
                            "status": "open",
                            "summary": "Need image verification",
                            "evidence_refs": ["image:assoc:tx:original"],
                        }
                    ],
                }
            }
        },
    )
    assert ms2.closure_state.overall_status == "open"
    assert len(ms2.closure_state.dimensions) == 1
    assert ms2.closure_state.dimensions[0].dimension_id == "layer_1_delta_convergence"

    ms3, _, _ = apply_state_patch(
        mission_state=ms2,
        resolution_state=rs,
        state_patch={
            "mission": {
                "closure_state": {
                    "dimensions": [
                        {
                            "dimension_id": "layer_1_delta_convergence",
                            "status": "closed",
                            "summary": "Image check complete",
                        },
                        {
                            "dimension_id": "layer_4_mapping_blocking_relevance",
                            "title": "Layer 4",
                            "status": "non_blocking",
                            "summary": "No remaining blocker",
                            "blocking": False,
                        },
                    ],
                    "opaque_payload": {"publish_ready": True},
                    "ready_to_publish": True,
                }
            }
        },
    )
    assert len(ms3.closure_state.dimensions) == 2
    dim1 = next(d for d in ms3.closure_state.dimensions if d.dimension_id == "layer_1_delta_convergence")
    assert dim1.status == "closed"
    assert dim1.evidence_refs == ["image:assoc:tx:original"]
    assert ms3.closure_state.ready_to_publish is True
    assert ms3.closure_state.opaque_payload["publish_ready"] is True


def test_mission_patch_rejects_invalid_closure_state_shape() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"mission": {"closure_state": {"dimensions": [{"title": "missing id"}]}}},
        )
    assert excinfo.value.reason_code == "closure_dimension_missing_id"


def test_closure_dimension_partial_update_preserves_determination() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "closure_state": {
                    "dimensions": [
                        {
                            "dimension_id": "layer_1_delta_convergence",
                            "title": "Layer 1",
                            "status": "in_review",
                            "determination": "provisional",
                        }
                    ]
                }
            }
        },
    )
    ms3, _, _ = apply_state_patch(
        mission_state=ms2,
        resolution_state=rs,
        state_patch={
            "mission": {
                "closure_state": {
                    "dimensions": [
                        {
                            "dimension_id": "layer_1_delta_convergence",
                            "status": "closed",
                        }
                    ]
                }
            }
        },
    )
    dim1 = next(d for d in ms3.closure_state.dimensions if d.dimension_id == "layer_1_delta_convergence")
    assert dim1.status == "closed"
    assert dim1.determination == "provisional"


def test_mission_patch_null_closure_state_resets_ledger() -> None:
    ms, rs = _base_states()
    ms, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission": {
                "closure_state": {
                    "overall_status": "blocked",
                    "dimensions": [
                        {
                            "dimension_id": "layer_1_delta_convergence",
                            "title": "Layer 1",
                            "status": "open",
                        }
                    ],
                }
            }
        },
    )
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"closure_state": None}},
    )
    assert ms2.closure_state.overall_status is None
    assert ms2.closure_state.dimensions == []


def test_invalid_item_rows_skipped() -> None:
    ms, rs = _base_states()
    _, rs2, skips = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {"item_id": "", "title": "x", "kind": "k", "status": "s"},
                    {
                        "item_id": "ok",
                        "title": "Valid",
                        "kind": "work_unit",
                        "status": "open",
                    },
                ],
            }
        },
    )
    assert len(rs2.items) == 1
    assert rs2.items[0].item_id == "ok"
    assert skips["resolution"]["items"] == {"missing_item_id": 1}


def test_empty_patch_noop() -> None:
    ms, rs = _base_states()
    ms2, rs2, skips_empty = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=None)
    assert ms2.mission_id == ms.mission_id
    assert rs2 is rs
    assert skips_empty["resolution"]["items"] == {}
    assert skips_empty["resolution"]["relations"] == {}


def test_skipped_item_and_relation_rows_reported() -> None:
    ms, rs = _base_states()
    _, rs2, skips = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    "not-a-dict",
                    {"item_id": "i1", "title": "A", "kind": "work_unit", "status": "open"},
                    {"item_id": "i2", "status": "open"},
                ],
                "relations": [
                    None,
                    {
                        "source_item_id": "i1",
                        "target_item_id": "i2",
                        "relation_type": "blocks",
                    },
                ],
            }
        },
    )
    assert {i.item_id for i in rs2.items} == {"i1"}
    assert len(rs2.relations) == 1
    assert skips["resolution"]["items"]["not_object"] == 1
    assert skips["resolution"]["items"]["validation_failed"] == 1
    assert skips["resolution"]["relations"]["not_object"] == 1


def test_relations_truncation_reports_cap_skip() -> None:
    ms, rs = _base_states()
    rel = {
        "source_item_id": "a",
        "target_item_id": "b",
        "relation_type": "blocks",
    }
    with patch.object(state_patch_apply_mod, "MAX_RESOLUTION_RELATIONS_TOTAL", 1):
        _, rs2, skips = apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"resolution": {"relations": [rel, rel]}},
        )
    assert len(rs2.relations) == 1
    assert skips["resolution"]["relations"]["truncated_to_cap"] == 1


# ---------------------------------------------------------------------------
# Summary field string shorthand tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("field_name", [
    "blocker_summary",
    "verification_summary",
    "waiting_summary",
    "continuity_summary",
    "mission_mode_summary",
])
def test_mission_summary_field_accepts_string_shorthand(field_name: str) -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {field_name: "Need clearer image evidence"}},
    )
    assert getattr(ms2, field_name) == {"summary": "Need clearer image evidence"}


def test_mission_summary_string_blank_normalizes_to_empty_dict() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"blocker_summary": "   "}},
    )
    assert ms2.blocker_summary == {}


def test_mission_summary_object_behavior_unchanged() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(update={"blocker_summary": {"prior": "value"}})
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"blocker_summary": {"new": "key"}}},
    )
    assert ms2.blocker_summary == {"prior": "value", "new": "key"}


def test_mission_summary_null_clears_to_empty_dict() -> None:
    ms, rs = _base_states()
    ms = ms.model_copy(update={"blocker_summary": {"prior": "value"}})
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"blocker_summary": None}},
    )
    assert ms2.blocker_summary == {}


def test_mission_summary_integer_still_rejected() -> None:
    """Non-string, non-dict, non-null values are still rejected."""
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"mission": {"blocker_summary": 42}},
        )
    assert "blocker_summary" in excinfo.value.reason_code


def test_mission_patch_accepts_work_universe_posture() -> None:
    ms, rs = _base_states()
    ms2, _, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={"mission": {"work_universe_posture": "believed_adequate"}},
    )
    assert ms2.work_universe_posture == "believed_adequate"


def test_mission_patch_rejects_invalid_work_universe_posture() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={"mission": {"work_universe_posture": "complete"}},
        )
    assert excinfo.value.reason_code == "work_universe_posture_invalid"


def test_state_patch_alias_keys_normalize_to_canonical_branches() -> None:
    ms, rs = _base_states()
    ms2, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "mission_state": {"active_mode": "reviewing", "work_universe_posture": "partial"},
            "resolution_state": {
                "active_item_id": "i-alias",
                "items": [
                    {
                        "item_id": "i-alias",
                        "title": "Alias item",
                        "kind": "work_unit",
                        "status": "open",
                    }
                ],
            },
        },
    )
    assert ms2.active_mode == "reviewing"
    assert ms2.work_universe_posture == "partial"
    assert rs2.active_item_id == "i-alias"
    assert len(rs2.items) == 1
    assert rs2.items[0].item_id == "i-alias"


def test_state_patch_alias_conflict_rejected() -> None:
    ms, rs = _base_states()
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=ms,
            resolution_state=rs,
            state_patch={
                "mission": {"active_mode": "canonical"},
                "mission_state": {"active_mode": "alias"},
            },
        )
    assert excinfo.value.reason_code == "state_patch_alias_conflict"


# ---------------------------------------------------------------------------
# Rich feedback / repair_targets seam
# ---------------------------------------------------------------------------

def test_derive_repair_targets_from_success_condition_reason_code() -> None:
    from harness.runtime.orchestration.state_patch_apply import _derive_repair_targets_from_feedback
    targets = _derive_repair_targets_from_feedback(reason_code="success_condition_missing_id")
    assert "repair_success_condition_row" in targets


def test_derive_repair_targets_from_closure_dimension_reason_code() -> None:
    from harness.runtime.orchestration.state_patch_apply import _derive_repair_targets_from_feedback
    targets = _derive_repair_targets_from_feedback(reason_code="closure_dimension_missing_id")
    assert "repair_closure_dimension_row" in targets
    targets2 = _derive_repair_targets_from_feedback(reason_code="closure_state_unknown_keys")
    assert "repair_closure_dimension_row" in targets2


def test_derive_repair_targets_from_mission_reason_code() -> None:
    from harness.runtime.orchestration.state_patch_apply import _derive_repair_targets_from_feedback
    targets = _derive_repair_targets_from_feedback(reason_code="mission_unknown_keys")
    assert "repair_mission_patch_shape" in targets


def test_derive_repair_targets_from_resolution_reason_code() -> None:
    from harness.runtime.orchestration.state_patch_apply import _derive_repair_targets_from_feedback
    for code in ("resolution_unknown_keys", "items_not_array", "relations_not_array"):
        targets = _derive_repair_targets_from_feedback(reason_code=code)
        assert "repair_resolution_patch_shape" in targets, f"missing target for {code}"


def test_derive_repair_targets_from_row_skip_details() -> None:
    from harness.runtime.orchestration.state_patch_apply import _derive_repair_targets_from_feedback
    skip_details_items = {"resolution": {"items": [{"reason_code": "missing_item_id"}]}}
    targets = _derive_repair_targets_from_feedback(row_skip_details=skip_details_items)
    assert "repair_resolution_item_rows" in targets

    skip_details_rels = {"resolution": {"relations": [{"reason_code": "validation_failed"}]}}
    targets2 = _derive_repair_targets_from_feedback(row_skip_details=skip_details_rels)
    assert "repair_resolution_relation_rows" in targets2


def test_derive_repair_targets_empty_for_unknown_reason_code() -> None:
    from harness.runtime.orchestration.state_patch_apply import _derive_repair_targets_from_feedback
    targets = _derive_repair_targets_from_feedback(reason_code="some_unrelated_code")
    assert targets == []


def test_build_state_patch_feedback_tracks_same_outcome_streak() -> None:
    from harness.runtime.orchestration.state_patch_apply import _build_state_patch_feedback
    fb1 = _build_state_patch_feedback(None, outcome="rejected", iteration=1, reason_code="bad_key")
    assert fb1["same_outcome_streak"] == 1

    fb2 = _build_state_patch_feedback(fb1, outcome="rejected", iteration=2, reason_code="bad_key")
    assert fb2["same_outcome_streak"] == 2
    assert fb2["same_reason_code_streak"] == 2

    fb3 = _build_state_patch_feedback(fb2, outcome="applied", iteration=3)
    assert fb3["same_outcome_streak"] == 1
    assert "same_reason_code_streak" not in fb3


def test_build_state_patch_feedback_tracks_last_applied_iteration() -> None:
    from harness.runtime.orchestration.state_patch_apply import _build_state_patch_feedback
    fb1 = _build_state_patch_feedback(None, outcome="rejected", iteration=1, reason_code="bad_key")
    assert "last_applied_iteration" not in fb1

    fb2 = _build_state_patch_feedback(fb1, outcome="applied", iteration=2)
    assert fb2["last_applied_iteration"] == 2

    fb3 = _build_state_patch_feedback(fb2, outcome="rejected", iteration=3, reason_code="bad_key")
    assert fb3["last_applied_iteration"] == 2  # preserved from prior applied


def test_build_state_patch_feedback_propagates_repair_hint_from_reason_code() -> None:
    from harness.runtime.orchestration.state_patch_apply import _build_state_patch_feedback
    fb = _build_state_patch_feedback(None, outcome="rejected", iteration=1, reason_code="success_condition_missing_id")
    # The feedback should have a repair_hint derived from the reason_code.
    assert "repair_hint" in fb
    assert fb["repair_hint"] is not None

    fb2 = _build_state_patch_feedback(None, outcome="rejected", iteration=1, reason_code="closure_dimension_missing_id")
    assert "repair_hint" in fb2

    fb3 = _build_state_patch_feedback(None, outcome="rejected", iteration=1, reason_code="mission_unknown_keys")
    assert "repair_hint" in fb3
