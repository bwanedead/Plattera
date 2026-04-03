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
