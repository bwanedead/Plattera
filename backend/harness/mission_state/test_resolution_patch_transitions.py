"""MAPDEP-BR-025: resolution patch lifecycle transition expansion."""

from __future__ import annotations

import copy
import json

import pytest

from harness.mission_state import (
    ResolutionCoveredUnit,
    ResolutionItem,
    new_mission_state,
    new_resolution_state,
)
from harness.mission_state.resolution_patch_transitions import (
    ResolutionPatchTransitionError,
    expand_resolution_patch_transitions,
)
from harness.runtime.orchestration.state_patch_apply import StatePatchError, apply_state_patch
from harness.runtime.orchestration.state_patch_consistency import (
    evaluate_state_patch_terminal_row_consistency,
    preview_state_patch_merge,
)


def _item(
    *,
    item_id: str = "bearing-group",
    status: str = "open",
    next_needed_step: str | None = "verify bearing",
    blocking: bool | None = True,
    requires_hitl: bool = True,
    no_further_progress: bool = True,
    covered_units: list[ResolutionCoveredUnit] | None = None,
) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=f"Title {item_id}",
        kind="group",
        status=status,
        next_needed_step=next_needed_step,
        blocking=blocking,
        requires_hitl=requires_hitl,
        no_further_progress=no_further_progress,
        covered_units=list(covered_units or []),
    )


def _unit(
    *,
    unit_id: str = "call-2-bearing",
    status: str = "open",
    next_needed_step: str | None = "verify unit",
    requires_hitl: bool = True,
    no_further_progress: bool = True,
) -> ResolutionCoveredUnit:
    return ResolutionCoveredUnit(
        unit_id=unit_id,
        title=f"Unit {unit_id}",
        status=status,
        next_needed_step=next_needed_step,
        requires_hitl=requires_hitl,
        no_further_progress=no_further_progress,
    )


def _seed_rs(items: list[ResolutionItem]):
    return new_resolution_state(items=items, active_item_id=items[0].item_id if items else None)


def _seed_ms(rs):
    return new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        objective="t",
        resolution_state=rs,
    )


def test_existing_parent_item_resolve_clears_all_parent_live_work_fields() -> None:
    sibling = _item(item_id="other-item", next_needed_step="keep", blocking=True)
    sibling_before = sibling.model_dump(mode="json")
    rs = _seed_rs(
        [
            _item(),
            sibling,
        ]
    )
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "transition": {"kind": "resolve"},
                    "determination": "earned",
                    "determined_value": "N 42° E",
                    "verification_basis": "Confirmed from the focused source observation.",
                    "evidence_refs": ["image:derived:abc"],
                    "closure_summary": "Source-supported transcription applied.",
                }
            ]
        }
    }
    _ms, out_rs, _ = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    item = next(i for i in out_rs.items if i.item_id == "bearing-group")
    assert item.status == "closed"
    assert item.next_needed_step is None
    assert item.requires_hitl is False
    assert item.no_further_progress is False
    assert item.blocking is False
    assert item.determination == "earned"
    assert item.determined_value == "N 42° E"
    assert item.verification_basis == "Confirmed from the focused source observation."
    assert item.evidence_refs == ["image:derived:abc"]
    assert item.closure_summary == "Source-supported transcription applied."
    other = next(i for i in out_rs.items if i.item_id == "other-item")
    assert other.model_dump(mode="json") == sibling_before
    dumped = json.dumps(out_rs.model_dump(mode="json"), ensure_ascii=False)
    assert "transition" not in dumped


def test_existing_covered_unit_resolve_clears_only_that_unit() -> None:
    keep_unit = _unit(unit_id="call-1-bearing", next_needed_step="keep unit")
    keep_before = keep_unit.model_dump(mode="json")
    sibling = _item(item_id="other-item", next_needed_step="keep sibling")
    sibling_before = sibling.model_dump(mode="json")
    target = _item(
        next_needed_step="parent still open",
        blocking=True,
        requires_hitl=True,
        no_further_progress=False,
        covered_units=[_unit(), keep_unit],
    )
    parent_before = {
        "status": target.status,
        "next_needed_step": target.next_needed_step,
        "blocking": target.blocking,
        "requires_hitl": target.requires_hitl,
    }
    rs = _seed_rs([target, sibling])
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "covered_units": [
                        {
                            "unit_id": "call-2-bearing",
                            "transition": {"kind": "resolve"},
                            "determination": "earned",
                            "determined_value": "N 42° E",
                            "verification_basis": "Confirmed from source evidence.",
                            "evidence_refs": ["image:derived:xyz"],
                        }
                    ],
                }
            ]
        }
    }
    _ms, out_rs, _ = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    item = next(i for i in out_rs.items if i.item_id == "bearing-group")
    assert item.status == parent_before["status"]
    assert item.next_needed_step == parent_before["next_needed_step"]
    assert item.blocking == parent_before["blocking"]
    assert item.requires_hitl == parent_before["requires_hitl"]
    resolved = next(u for u in item.covered_units if u.unit_id == "call-2-bearing")
    assert resolved.status == "closed"
    assert resolved.next_needed_step is None
    assert resolved.requires_hitl is False
    assert resolved.no_further_progress is False
    assert resolved.determination == "earned"
    assert resolved.determined_value == "N 42° E"
    kept = next(u for u in item.covered_units if u.unit_id == "call-1-bearing")
    assert kept.model_dump(mode="json") == keep_before
    other = next(i for i in out_rs.items if i.item_id == "other-item")
    assert other.model_dump(mode="json") == sibling_before


def test_missing_item_transition_refuses_without_mutation() -> None:
    rs = _seed_rs([_item()])
    before = rs.model_dump(mode="json")
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [{"item_id": "missing-item", "transition": {"kind": "resolve"}}]
        }
    }
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert excinfo.value.reason_code == "transition_target_missing"
    assert rs.model_dump(mode="json") == before


def test_missing_covered_unit_transition_refuses_without_mutation() -> None:
    rs = _seed_rs([_item(covered_units=[_unit()])])
    before = rs.model_dump(mode="json")
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "covered_units": [
                        {"unit_id": "missing-unit", "transition": {"kind": "resolve"}}
                    ],
                }
            ]
        }
    }
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert excinfo.value.reason_code == "transition_target_missing"
    assert rs.model_dump(mode="json") == before


@pytest.mark.parametrize(
    "transition,reason",
    [
        ({"kind": "reopen"}, "transition_kind_unsupported"),
        ({"kind": "resolve", "extra": True}, "transition_unknown_fields"),
        ("resolve", "transition_invalid"),
        ({}, "transition_kind_unsupported"),
        ({"kind": 1}, "transition_kind_unsupported"),
    ],
)
def test_unknown_or_malformed_transition_refuses(transition: object, reason: str) -> None:
    rs = _seed_rs([_item()])
    before = rs.model_dump(mode="json")
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [{"item_id": "bearing-group", "transition": transition}]
        }
    }
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert excinfo.value.reason_code == reason
    assert rs.model_dump(mode="json") == before


def test_transition_plus_direct_consequence_fields_refuse() -> None:
    rs = _seed_rs([_item()])
    before = rs.model_dump(mode="json")
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "transition": {"kind": "resolve"},
                    "status": "closed",
                    "next_needed_step": None,
                }
            ]
        }
    }
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert excinfo.value.reason_code == "transition_consequence_fields_conflict"
    assert rs.model_dump(mode="json") == before


def test_unit_transition_plus_direct_consequence_fields_refuse() -> None:
    rs = _seed_rs([_item(covered_units=[_unit()])])
    before = rs.model_dump(mode="json")
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "covered_units": [
                        {
                            "unit_id": "call-2-bearing",
                            "transition": {"kind": "resolve"},
                            "status": "closed",
                            "requires_hitl": False,
                        }
                    ],
                }
            ]
        }
    }
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert excinfo.value.reason_code == "transition_consequence_fields_conflict"
    assert rs.model_dump(mode="json") == before


def test_resolve_preserves_existing_earned_semantic_fields_without_restatement() -> None:
    item = ResolutionItem(
        item_id="bearing-group",
        title="Title bearing-group",
        kind="group",
        status="open",
        determination="earned",
        determined_value="N 42° E",
        verification_basis="Confirmed from focused source observation.",
        evidence_refs=["image:derived:abc"],
        closure_summary="Source-supported transcription applied.",
        next_needed_step="stale clear me",
        blocking=True,
        requires_hitl=True,
        no_further_progress=True,
    )
    rs = _seed_rs([item])
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [{"item_id": "bearing-group", "transition": {"kind": "resolve"}}]
        }
    }
    _ms, out_rs, _ = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    resolved = out_rs.items[0]
    assert resolved.status == "closed"
    assert resolved.next_needed_step is None
    assert resolved.requires_hitl is False
    assert resolved.no_further_progress is False
    assert resolved.blocking is False
    assert resolved.determination == "earned"
    assert resolved.determined_value == "N 42° E"
    assert resolved.verification_basis == "Confirmed from focused source observation."
    assert resolved.evidence_refs == ["image:derived:abc"]
    assert resolved.closure_summary == "Source-supported transcription applied."


def test_malformed_transition_kinds_are_not_classified_as_semantic_intent() -> None:
    from harness.runtime.orchestration.state_patch_apply import _detect_semantic_intent_kinds

    assert _detect_semantic_intent_kinds(
        state_patch={
            "resolution": {
                "items": [{"item_id": "bearing-group", "transition": {"kind": "resolve"}}]
            }
        },
        hitl_consumed_prompt_ids=(),
    ) == ["item_status_change"]
    assert _detect_semantic_intent_kinds(
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "bearing-group",
                        "covered_units": [
                            {"unit_id": "u1", "transition": {"kind": "resolve"}}
                        ],
                    }
                ]
            }
        },
        hitl_consumed_prompt_ids=(),
    ) == ["unit_status_change"]

    malformed = [
        {"kind": " resolve"},
        {"kind": "Resolve"},
        {"kind": "reopen"},
        {"kind": "resolve", "extra": True},
        "resolve",
        {"kind": 1},
        {},
    ]
    for transition in malformed:
        kinds = _detect_semantic_intent_kinds(
            state_patch={
                "resolution": {
                    "items": [{"item_id": "bearing-group", "transition": transition}]
                }
            },
            hitl_consumed_prompt_ids=(),
        )
        assert "item_status_change" not in kinds
        assert "unit_status_change" not in kinds

    rs = _seed_rs([_item()])
    before = rs.model_dump(mode="json")
    with pytest.raises(StatePatchError) as excinfo:
        apply_state_patch(
            mission_state=_seed_ms(rs),
            resolution_state=rs,
            state_patch={
                "resolution": {
                    "items": [
                        {
                            "item_id": "bearing-group",
                            "transition": {"kind": "resolve", "extra": True},
                        }
                    ]
                }
            },
        )
    assert excinfo.value.reason_code == "transition_unknown_fields"
    assert rs.model_dump(mode="json") == before


def test_preview_and_committed_merge_produce_same_effective_row() -> None:
    rs = _seed_rs([_item()])
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "transition": {"kind": "resolve"},
                    "determination": "earned",
                }
            ]
        }
    }
    preview = preview_state_patch_merge(
        mission_state=ms, resolution_state=rs, state_patch=patch
    )
    assert preview is not None
    _pms, preview_rs = preview
    _cms, commit_rs, _ = apply_state_patch(
        mission_state=ms, resolution_state=rs, state_patch=patch
    )
    preview_item = next(i for i in preview_rs.items if i.item_id == "bearing-group")
    commit_item = next(i for i in commit_rs.items if i.item_id == "bearing-group")
    assert preview_item.model_dump(mode="json") == commit_item.model_dump(mode="json")


def test_resolved_transition_does_not_trigger_terminal_row_live_work_conflict() -> None:
    rs = _seed_rs([_item()])
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [{"item_id": "bearing-group", "transition": {"kind": "resolve"}}]
        }
    }
    assert (
        evaluate_state_patch_terminal_row_consistency(
            mission_state=ms,
            resolution_state=rs,
            state_patch=patch,
        )
        is None
    )


def test_sparse_patch_without_transition_unchanged() -> None:
    rs = _seed_rs([_item(next_needed_step="verify")])
    ms = _seed_ms(rs)
    patch = {
        "resolution": {
            "items": [
                {
                    "item_id": "bearing-group",
                    "status": "closed",
                    "next_needed_step": None,
                    "requires_hitl": False,
                    "no_further_progress": False,
                    "blocking": False,
                }
            ]
        }
    }
    assert (
        evaluate_state_patch_terminal_row_consistency(
            mission_state=ms,
            resolution_state=rs,
            state_patch=patch,
        )
        is None
    )
    _ms, out_rs, _ = apply_state_patch(mission_state=ms, resolution_state=rs, state_patch=patch)
    assert out_rs.items[0].status == "closed"
    assert out_rs.items[0].next_needed_step is None


def test_expand_leaves_input_patch_transition_intact_when_expanding() -> None:
    """Expansion returns a new resolution branch; caller patch retains transition."""
    rs = _seed_rs([_item()])
    patch = {
        "resolution": {
            "items": [{"item_id": "bearing-group", "transition": {"kind": "resolve"}}]
        }
    }
    original = copy.deepcopy(patch)
    expanded = expand_resolution_patch_transitions(resolution_state=rs, state_patch=patch)
    assert patch == original
    assert "transition" not in expanded["resolution"]["items"][0]
    assert expanded["resolution"]["items"][0]["status"] == "closed"
    with pytest.raises(ResolutionPatchTransitionError):
        expand_resolution_patch_transitions(
            resolution_state=rs,
            state_patch={
                "resolution": {
                    "items": [
                        {
                            "item_id": "bearing-group",
                            "transition": {"kind": "resolve"},
                            "blocking": True,
                        }
                    ]
                }
            },
        )
