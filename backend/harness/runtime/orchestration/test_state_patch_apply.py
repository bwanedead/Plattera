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


def test_item_partial_update_preserves_sequence_metadata() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "i-seq",
                        "title": "Sequenced item",
                        "kind": "claim",
                        "status": "open",
                        "sequence_scope": "lane-a",
                        "sequence_index": 2,
                    }
                ],
            }
        },
    )
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={"resolution": {"items": [{"item_id": "i-seq", "status": "in_review"}]}},
    )
    assert rs3.items[0].status == "in_review"
    assert rs3.items[0].sequence_scope == "lane-a"
    assert rs3.items[0].sequence_index == 2


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


def test_covered_units_upsert_by_unit_id_and_overlay_fields() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "title": "Group",
                        "kind": "claim_group",
                        "status": "open",
                        "structure_kind": "group",
                        "covered_units": [
                            {
                                "unit_id": "g1-u1",
                                "title": "Unit one",
                                "status": "open",
                                "verification_basis": "BASIS_ONE",
                                "evidence_refs": ["artifact://e1"],
                            },
                            {
                                "unit_id": "g1-u2",
                                "title": "Unit two",
                                "status": "open",
                            },
                        ],
                    }
                ],
            }
        },
    )
    assert len(rs2.items[0].covered_units) == 2
    assert rs2.items[0].covered_units[0].unit_id == "g1-u1"

    # Per-field overlay on one unit; other unit and omitted fields unchanged.
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "covered_units": [
                            {
                                "unit_id": "g1-u1",
                                "status": "closed",
                                "determination": "earned",
                            }
                        ],
                    }
                ],
            }
        },
    )
    units = {u.unit_id: u for u in rs3.items[0].covered_units}
    assert units["g1-u1"].status == "closed"
    assert units["g1-u1"].determination == "earned"
    assert units["g1-u1"].title == "Unit one"
    assert units["g1-u1"].verification_basis == "BASIS_ONE"
    assert units["g1-u1"].evidence_refs == ["artifact://e1"]
    assert units["g1-u2"].status == "open"
    assert units["g1-u2"].title == "Unit two"


def test_covered_units_empty_list_does_not_wipe_prior_units() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "title": "Group",
                        "kind": "claim_group",
                        "status": "open",
                        "covered_units": [
                            {"unit_id": "u1", "title": "U One"},
                        ],
                    }
                ],
            }
        },
    )
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={"resolution": {"items": [{"item_id": "g1", "covered_units": []}]}},
    )
    assert [u.unit_id for u in rs3.items[0].covered_units] == ["u1"]


def test_covered_units_new_unit_requires_unit_id_and_title() -> None:
    ms, rs = _base_states()
    _, rs2, skips = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "title": "Group",
                        "kind": "claim_group",
                        "status": "open",
                        "covered_units": [
                            {"unit_id": "", "title": "No id"},
                        ],
                    }
                ],
            }
        },
    )
    # Whole item row was skipped due to invalid covered_unit.
    assert skips["resolution"]["items"].get("validation_failed", 0) == 1
    assert rs2.items == []

    _, rs3, skips2 = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "title": "Group",
                        "kind": "claim_group",
                        "status": "open",
                        "covered_units": [
                            {"unit_id": "u1"},  # missing title
                        ],
                    }
                ],
            }
        },
    )
    assert skips2["resolution"]["items"].get("validation_failed", 0) == 1
    assert rs3.items == []


def test_covered_units_accept_work_graph_value_fields_and_overlay() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "title": "Group",
                        "kind": "claim_group",
                        "status": "open",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "NW bearing",
                                "label": "nw-bearing",
                                "value_kind": "bearing",
                                "candidate_values": ["N 2 W", "N 4 W"],
                                "status": "open",
                            }
                        ],
                    }
                ],
            }
        },
    )
    unit = rs2.items[0].covered_units[0]
    assert unit.label == "nw-bearing"
    assert unit.value_kind == "bearing"
    assert unit.candidate_values == ["N 2 W", "N 4 W"]
    assert unit.determined_value is None

    # Sparse patch: only unit_id + determined_value; other fields preserved.
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "covered_units": [
                            {"unit_id": "u1", "determined_value": "N 4 W"}
                        ],
                    }
                ],
            }
        },
    )
    unit3 = rs3.items[0].covered_units[0]
    assert unit3.determined_value == "N 4 W"
    assert unit3.label == "nw-bearing"
    assert unit3.value_kind == "bearing"
    assert unit3.candidate_values == ["N 2 W", "N 4 W"]
    assert unit3.title == "NW bearing"


def test_covered_units_candidate_values_replaced_when_supplied() -> None:
    ms, rs = _base_states()
    _, rs2, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "title": "Group",
                        "kind": "claim_group",
                        "status": "open",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "U One",
                                "candidate_values": ["a", "b"],
                            }
                        ],
                    }
                ],
            }
        },
    )
    _, rs3, _ = apply_state_patch(
        mission_state=ms,
        resolution_state=rs2,
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "g1",
                        "covered_units": [
                            {"unit_id": "u1", "candidate_values": ["a", "b", "c"]}
                        ],
                    }
                ],
            }
        },
    )
    assert rs3.items[0].covered_units[0].candidate_values == ["a", "b", "c"]


# ---------------------------------------------------------------------------
# Deep nested validation feedback (Brief 1, item 1)
# ---------------------------------------------------------------------------


def _seed_item(rs, *, item_id: str = "i1") -> None:
    """Seed a base resolution item the covered_units rows can attach to."""
    pass  # state setup happens in _apply_with_feedback below


def _apply_with_feedback(state_patch, *, hitl_consumed_prompt_ids=(), mem=None, iteration=1):
    """Apply a state_patch via the loop-memory pipeline so feedback is observable.

    When ``mem`` is provided, the patch is applied against that existing memory
    so multiple calls compose. Otherwise a fresh memory is created.
    """
    from harness.runtime.memory import LoopMemoryState
    from harness.runtime.orchestration.contracts import ActionPlan
    from harness.runtime.orchestration.state_patch_apply import (
        apply_action_plan_state_patch_to_loop_memory,
    )

    if mem is None:
        mem = LoopMemoryState()
    plan = ActionPlan(
        state_patch=dict(state_patch) if state_patch else None,
        rationale="t",
        hitl_consumed_prompt_ids=tuple(hitl_consumed_prompt_ids),
    )
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem,
        action_plan=plan,
        tracer=None,
        iteration=iteration,
        gate="test",
    )
    return mem, mem.continuity.state_patch_feedback


def _seed_item_i1(mem):
    return _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {"item_id": "i1", "title": "First", "kind": "work_unit", "status": "open"}
                ]
            }
        },
        mem=mem,
        iteration=1,
    )


def test_covered_unit_overlong_determined_value_reports_path_and_bound() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    overlong = "x" * 912
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "T",
                                "determined_value": overlong,
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    # The item itself was skipped because the covered_unit failed validation.
    details = (fb.get("row_skip_details") or {}).get("resolution") or {}
    items = details.get("items") or []
    assert items, "expected per-row skip detail"
    detail0 = items[0]
    assert detail0["row_id"] == "i1"
    errors = detail0.get("validation_errors") or []
    assert any(
        "covered_units[u1].determined_value" in e and "string too long" in e and "912" in e and "400" in e
        for e in errors
    ), errors


def test_covered_unit_missing_title_reports_required() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [{"unit_id": "u1"}],  # missing title
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    errors = (
        (((fb.get("row_skip_details") or {}).get("resolution") or {}).get("items") or [{}])[0]
        .get("validation_errors")
        or []
    )
    assert any("covered_units[u1].title" in e and "required" in e for e in errors), errors


def test_covered_unit_forbidden_field_reports_extra_forbidden() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "T",
                                "primary_evidence_ref": "artifact://x",
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    errors = (
        (((fb.get("row_skip_details") or {}).get("resolution") or {}).get("items") or [{}])[0]
        .get("validation_errors")
        or []
    )
    assert any(
        "covered_units[u1].primary_evidence_ref" in e and "extra field forbidden" in e
        for e in errors
    ), errors


def test_valid_covered_unit_still_applies_cleanly() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {"unit_id": "u1", "title": "ok", "determined_value": "v"}
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    assert fb.get("outcome") == "applied"
    assert not fb.get("skipped_resolution_rows")


# ---------------------------------------------------------------------------
# Semantic repair debt + HITL stickiness (Brief 1, items 2 + 3)
# ---------------------------------------------------------------------------


def test_failed_hitl_integration_creates_repair_debt() -> None:
    # Patch is structurally invalid (unknown top-level key) so the whole patch
    # is rejected. The plan also tried to consume a HITL prompt id.
    _, fb = _apply_with_feedback(
        {"transcript_edit": {}},
        hitl_consumed_prompt_ids=["hitl-abc"],
    )
    assert fb["outcome"] == "rejected"
    debt = fb.get("semantic_repair_debt") or []
    assert "hitl_consumed_prompt_ids" in debt
    pending = fb.get("pending_hitl_integration_prompt_ids") or []
    assert "hitl-abc" in pending


def test_failed_determined_value_creates_repair_debt_via_skipped_rows() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "t",
                                "determined_value": "x" * 800,
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    assert fb.get("skipped_resolution_rows")
    debt = fb.get("semantic_repair_debt") or []
    assert "determined_value" in debt


def test_trivial_invalid_patch_does_not_create_semantic_repair_debt() -> None:
    # Unknown resolution key triggers rejection but the patch carries no
    # meaningful intent fields, so debt should remain empty.
    _, fb = _apply_with_feedback(
        {"resolution": {"items": [], "extra": 1}},
    )
    assert fb["outcome"] == "rejected"
    assert not fb.get("semantic_repair_debt")
    assert not fb.get("pending_hitl_integration_prompt_ids")


# ---------------------------------------------------------------------------
# Brief 2: evidence_locators schema (image_region, text_span, json_path, invalid box)
# ---------------------------------------------------------------------------


def test_covered_unit_accepts_image_region_locator() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "atom",
                                "evidence_refs": ["artifact://crop"],
                                "evidence_locators": [
                                    {
                                        "ref_id": "artifact://crop",
                                        "locator_kind": "image_region",
                                        "target": "determined_value",
                                        "label": "atom-region",
                                        "box_norm": [0.42, 0.31, 0.56, 0.39],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    assert fb["outcome"] == "applied"
    assert not fb.get("skipped_resolution_rows")
    unit = mem.continuity.resolution_state.items[0].covered_units[0]
    assert unit.evidence_locators[0].locator_kind == "image_region"
    assert unit.evidence_locators[0].box_norm == [0.42, 0.31, 0.56, 0.39]


def test_covered_unit_accepts_text_span_and_json_path_locator() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "atom",
                                "evidence_refs": ["artifact://log", "artifact://api-out"],
                                "evidence_locators": [
                                    {
                                        "ref_id": "artifact://log",
                                        "locator_kind": "text_span",
                                        "line_start": 12,
                                        "line_end": 14,
                                    },
                                    {
                                        "ref_id": "artifact://api-out",
                                        "locator_kind": "json_path",
                                        "json_path": "$.results[0].value",
                                    },
                                ],
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    assert fb["outcome"] == "applied"
    locs = mem.continuity.resolution_state.items[0].covered_units[0].evidence_locators
    assert {l.locator_kind for l in locs} == {"text_span", "json_path"}


def test_inverted_box_norm_rejected_with_path() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "atom",
                                "evidence_locators": [
                                    {
                                        "ref_id": "artifact://crop",
                                        "locator_kind": "image_region",
                                        "box_norm": [0.8, 0.1, 0.2, 0.3],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    errors = (
        (((fb.get("row_skip_details") or {}).get("resolution") or {}).get("items") or [{}])[0]
        .get("validation_errors")
        or []
    )
    assert any("box_norm" in e and "x_min" in e for e in errors), errors


def test_inverted_line_span_rejected() -> None:
    from harness.mission_state import EvidenceLocator
    import pytest
    with pytest.raises(Exception) as exc:
        EvidenceLocator(
            ref_id="artifact://log",
            locator_kind="text_span",
            line_start=20,
            line_end=10,
        )
    assert "line_start" in str(exc.value) and "line_end" in str(exc.value)


def test_inverted_char_span_rejected() -> None:
    from harness.mission_state import EvidenceLocator
    import pytest
    with pytest.raises(Exception) as exc:
        EvidenceLocator(
            ref_id="artifact://log",
            locator_kind="text_span",
            char_start=200,
            char_end=10,
        )
    assert "char_start" in str(exc.value) and "char_end" in str(exc.value)


def test_invalid_box_norm_surfaces_validation_error_with_path() -> None:
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    # Three floats instead of four → fails min_length / max_length validation.
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "atom",
                                "evidence_locators": [
                                    {
                                        "ref_id": "artifact://crop",
                                        "locator_kind": "image_region",
                                        "box_norm": [0.1, 0.2, 0.3],
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    errors = (
        (((fb.get("row_skip_details") or {}).get("resolution") or {}).get("items") or [{}])[0]
        .get("validation_errors")
        or []
    )
    assert any(
        "covered_units[u1].evidence_locators" in e and "box_norm" in e for e in errors
    ), errors


def test_unrelated_clean_apply_does_not_clear_unrepaired_debt() -> None:
    """A clean apply that does not address the failed semantic intent must not
    silently clear the debt; only kinds the patch plausibly repairs are cleared."""
    from harness.runtime.memory import LoopMemoryState
    mem = LoopMemoryState()
    _seed_item_i1(mem)
    # Fail a determined_value persistence → debt records `determined_value`.
    _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {"unit_id": "u1", "title": "t", "determined_value": "x" * 800}
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    debt_after_fail = mem.continuity.state_patch_feedback.get("semantic_repair_debt") or []
    assert "determined_value" in debt_after_fail

    # Apply an unrelated clean patch (just a status touch on a different concern).
    _apply_with_feedback(
        {"resolution": {"items": [{"item_id": "i1", "notes": "ok"}]}},
        mem=mem,
        iteration=3,
    )
    fb = mem.continuity.state_patch_feedback
    assert fb["outcome"] == "applied"
    assert "determined_value" in (fb.get("semantic_repair_debt") or []), fb

    # Now apply a patch that actually addresses determined_value → debt clears.
    _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {"unit_id": "u1", "title": "t", "determined_value": "v"}
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=4,
    )
    fb2 = mem.continuity.state_patch_feedback
    assert fb2["outcome"] == "applied"
    assert "determined_value" not in (fb2.get("semantic_repair_debt") or [])


def test_successful_clean_apply_clears_pending_hitl_integration() -> None:
    # First, fail with consumed-id attempt → debt is recorded.
    from harness.runtime.memory import LoopMemoryState
    from harness.runtime.orchestration.contracts import ActionPlan
    from harness.runtime.orchestration.state_patch_apply import (
        apply_action_plan_state_patch_to_loop_memory,
    )

    mem = LoopMemoryState()
    bad_plan = ActionPlan(
        state_patch={"transcript_edit": {}},
        rationale="t",
        hitl_consumed_prompt_ids=("hitl-abc",),
    )
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem, action_plan=bad_plan, tracer=None, iteration=1
    )
    assert "hitl-abc" in mem.continuity.state_patch_feedback.get(
        "pending_hitl_integration_prompt_ids", []
    )

    # Then apply a clean patch that consumes the same id.
    good_plan = ActionPlan(
        state_patch={
            "resolution": {
                "items": [
                    {"item_id": "i1", "title": "ok", "kind": "work_unit", "status": "open"}
                ]
            }
        },
        rationale="t",
        hitl_consumed_prompt_ids=("hitl-abc",),
    )
    apply_action_plan_state_patch_to_loop_memory(
        loop_memory=mem, action_plan=good_plan, tracer=None, iteration=2
    )
    fb = mem.continuity.state_patch_feedback
    assert fb["outcome"] == "applied"
    assert "hitl-abc" not in fb.get("pending_hitl_integration_prompt_ids", [])


# ---------------------------------------------------------------------------
# Brief 3: Field-level patch salvage (overlong optional prose fields)
# ---------------------------------------------------------------------------


def test_overlong_closure_summary_does_not_skip_valid_item_update() -> None:
    # closure_summary exceeds its 240-char max but all other fields are valid.
    # The row must be applied (with closure_summary omitted) rather than skipped.
    from harness.runtime.memory import LoopMemoryState

    mem = LoopMemoryState()
    _seed_item_i1(mem)
    mem2, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "status": "closed",
                        "closure_summary": "x" * 500,  # exceeds 240-char max
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    # Outcome must be applied — the row was salvaged, not skipped.
    assert fb["outcome"] == "applied"
    assert not fb.get("skipped_resolution_rows")
    # The item's status must have been updated.
    item = mem2.continuity.resolution_state.items[0]
    assert item.status == "closed"
    # closure_summary was omitted (not stored).
    assert item.closure_summary is None
    # Salvage event surfaces in feedback.
    salvaged = fb.get("salvaged_rows") or []
    assert len(salvaged) == 1
    assert salvaged[0]["row_id"] == "i1"
    assert any("closure_summary" in e for e in salvaged[0]["omitted_invalid_fields"])


def test_overlong_notes_or_summary_is_omitted_with_feedback() -> None:
    # Both notes and summary overlong: both omitted, valid fields applied, feedback names both.
    from harness.runtime.memory import LoopMemoryState

    mem = LoopMemoryState()
    _seed_item_i1(mem)
    mem2, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "notes": "n" * 600,      # exceeds 500-char max
                        "summary": "s" * 600,    # exceeds 500-char max
                        "status": "in_progress",
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    assert fb["outcome"] == "applied"
    item = mem2.continuity.resolution_state.items[0]
    assert item.status == "in_progress"
    assert item.notes is None
    assert item.summary is None
    salvaged = fb.get("salvaged_rows") or []
    assert len(salvaged) == 1
    omitted_fields_str = " ".join(salvaged[0]["omitted_invalid_fields"])
    assert "notes" in omitted_fields_str
    assert "summary" in omitted_fields_str


def test_invalid_determined_value_is_not_salvaged_for_earned_unit() -> None:
    # determined_value on a covered_unit is a semantic field — overlong → skip, not salvage.
    from harness.runtime.memory import LoopMemoryState

    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "covered_units": [
                            {
                                "unit_id": "u1",
                                "title": "Unit one",
                                "determined_value": "d" * 500,  # exceeds 400-char max
                            }
                        ],
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    # Row must be skipped, not salvaged.
    assert fb.get("skipped_resolution_rows")
    assert not fb.get("salvaged_rows")


def test_invalid_identity_field_still_skips_row() -> None:
    # An invalid identity field (title too short after stripping) must skip, not salvage.
    from harness.runtime.memory import LoopMemoryState

    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "title": "",    # min_length=1 violated — not salvageable
                        "status": "closed",
                        "closure_summary": "Fine summary",
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    assert fb.get("skipped_resolution_rows")
    assert not fb.get("salvaged_rows")


def test_salvage_feedback_names_exact_field_path() -> None:
    # Salvage event must carry a path that includes the item anchor and field name.
    from harness.runtime.memory import LoopMemoryState

    mem = LoopMemoryState()
    _seed_item_i1(mem)
    _, fb = _apply_with_feedback(
        {
            "resolution": {
                "items": [
                    {
                        "item_id": "i1",
                        "closure_summary": "c" * 300,  # exceeds 240-char max
                    }
                ]
            }
        },
        mem=mem,
        iteration=2,
    )
    salvaged = fb.get("salvaged_rows") or []
    assert salvaged, "expected salvage event"
    event = salvaged[0]
    assert event["path"].startswith("resolution.items[i1]")
    assert event["row_id"] == "i1"
    # omitted_invalid_fields must name the field precisely.
    omitted = " ".join(event["omitted_invalid_fields"])
    assert "closure_summary" in omitted
    assert event.get("note")
