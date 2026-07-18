"""Tests for derived atom evidence worklist (exact joins only)."""

from __future__ import annotations

import json

from harness.runtime.memory.atom_evidence_worklist import build_atom_evidence_worklist
from harness.runtime.memory.continuity_journal import build_kernel_step_result_record
from tooling.mapping.transcript_edit.point_crop_set_projection import project_point_crop_set_summary
from harness.runtime.orchestration.subtasks.delegate_result_refs import build_delegate_result_record


def _resolution_state(*, items: list[dict]) -> dict:
    return {"schema_version": "1", "items": items}


def _group_item(*, item_id: str, units: list[dict]) -> dict:
    return {
        "item_id": item_id,
        "title": f"Group {item_id}",
        "kind": "group",
        "status": "open",
        "covered_units": units,
    }


def _unit(
    *,
    unit_id: str,
    status: str = "open",
    determination: str | None = None,
    evidence_refs: list[str] | None = None,
    determined_value: str | None = None,
    candidate_values: list[str] | None = None,
) -> dict:
    row: dict = {
        "unit_id": unit_id,
        "title": unit_id.replace("_", " "),
        "status": status,
        "determination": determination,
        "evidence_refs": evidence_refs or [],
    }
    if determined_value is not None:
        row["determined_value"] = determined_value
    if candidate_values is not None:
        row["candidate_values"] = candidate_values
    return row


def _crop_outputs(
    *,
    aliases: list[str],
    turn: int = 6,
    target_atom_ids: list[str] | None = None,
    target_hints: list[str] | None = None,
) -> dict:
    points = []
    for i, alias in enumerate(aliases):
        point = {
            "letter": chr(ord("A") + i),
            "alias": alias,
            "crop_ref": f"image:derived:crop-{alias}",
            "point_norm": [0.1 * i, 0.2],
            "box_norm": [0.1, 0.2, 0.3, 0.4],
            "absolute_path": f"C:\\secret\\{alias}.png",
            "b64": "strip-me",
        }
        if target_atom_ids and i < len(target_atom_ids) and target_atom_ids[i]:
            point["target_atom_id"] = target_atom_ids[i]
        if target_hints and i < len(target_hints) and target_hints[i]:
            point["target_hint"] = target_hints[i]
        points.append(point)
    return {
        "derived_ref_id": "image:derived:master-parcel1",
        "sub_action": "point_crops",
        "crop_set": {
            "master_overlay_ref": "image:derived:master-parcel1",
            "source_ref": "image:assoc:tx-1:original",
            "points": points,
        },
    }


def _result_record(*, turn: int, outputs: dict) -> dict:
    return build_kernel_step_result_record(
        kernel_turn_index=turn,
        action_type="transform_artifact",
        execution_state="executed",
        execution_reason_code=None,
        latest_refs_snapshot={},
        outputs=outputs,
        artifact_refs=[],
    )


def _atom(worklist: dict, atom_id: str) -> dict:
    for row in worklist["atoms"]:
        if row["atom_id"] == atom_id:
            return row
    raise AssertionError(f"atom {atom_id!r} not in worklist")


def _delegate_record(
    *,
    turn: int,
    alias: str,
    status: str = "completed",
    context_refs: list[str] | None = None,
    action_index: int = 1,
) -> dict:
    ref_id = f"subtask:turn{turn}:{alias}"
    return build_delegate_result_record(
        ref_id=ref_id,
        turn_index=turn,
        alias=alias,
        action_index=action_index,
        action_inputs={
            "profile": "transcript_edit.visual_source_observation",
            "task": "read visible call",
            "context_refs": context_refs or [],
        },
        outputs={
            "action_type": "delegate_subtask",
            "status": status,
            "result": {"task_response": "observed"},
            "subtask_trace": {"raw_prompt_text": "strip", "b64": "strip"},
        },
    )


def test_direct_alias_crop_maps_to_covered_unit_atom() -> None:
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1_visible_calls",
                units=[_unit(unit_id="p1_acreage", candidate_values=["1.9 acres"])],
            )
        ]
    )
    records = [_result_record(turn=6, outputs=_crop_outputs(aliases=["p1_acreage"]))]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    assert worklist["kind"] == "atom_evidence_worklist"
    atom = _atom(worklist, "p1_acreage")
    assert atom["atom_id"] == "p1_acreage"
    assert atom["parent_item_id"] == "parcel_1_visible_calls"
    assert atom["utilization_status"] == "open_packet_ready_unused"
    assert atom["packet_refs"][0]["match_kind"] == "direct_alias_match"
    assert atom["packet_refs"][0]["source_alias"] == "p1_acreage"
    assert atom["packet_refs"][0]["crop_ref"] == "image:derived:crop-p1_acreage"


def test_target_atom_id_joins_even_when_alias_differs() -> None:
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1_visible_calls",
                units=[_unit(unit_id="p1_call1_distance", candidate_values=["542 feet"])],
            )
        ]
    )
    records = [
        _result_record(
            turn=6,
            outputs=_crop_outputs(
                aliases=["different_alias"],
                target_atom_ids=["p1_call1_distance"],
                target_hints=["542 feet"],
            ),
        )
    ]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    atom = _atom(worklist, "p1_call1_distance")
    assert atom["packet_refs"][0]["match_kind"] == "target_atom_id_match"
    assert atom["packet_refs"][0]["source_alias"] == "different_alias"
    assert atom["packet_refs"][0]["target_atom_id"] == "p1_call1_distance"
    assert atom["packet_refs"][0]["target_hint"] == "542 feet"


def test_unknown_target_atom_id_surfaces_in_unmatched_packet_refs() -> None:
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1_visible_calls",
                units=[_unit(unit_id="p1_acreage")],
            )
        ]
    )
    records = [
        _result_record(
            turn=6,
            outputs=_crop_outputs(
                aliases=["distance_probe_alias"],
                target_atom_ids=["missing_atom"],
                target_hints=["542 feet"],
            ),
        )
    ]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    assert worklist["unmatched_packet_refs"]
    unmatched = worklist["unmatched_packet_refs"][0]
    assert unmatched["target_atom_id"] == "missing_atom"
    assert unmatched["target_hint"] == "542 feet"


def test_ten_crops_four_delegates_six_packet_ready_unused() -> None:
    aliases = [f"p1_atom_{i}" for i in range(10)]
    units = [_unit(unit_id=alias) for alias in aliases]
    state = _resolution_state(items=[_group_item(item_id="parcel_1", units=units)])
    records = [_result_record(turn=6, outputs=_crop_outputs(aliases=aliases))]
    delegates = [
        _delegate_record(
            turn=7,
            alias=aliases[i],
            context_refs=[f"image:derived:crop-{aliases[i]}"],
        )
        for i in range(4)
    ]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
        delegate_result_records=delegates,
    )
    assert worklist["counts"]["packet_ready_unused"] == 6
    assert worklist["counts"]["packet_used_not_determined"] == 4
    ready = [a for a in worklist["atoms"] if a["utilization_status"] == "open_packet_ready_unused"]
    assert len(ready) == 6


def test_delegate_ambiguous_or_failed_does_not_close_open_atom() -> None:
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1",
                units=[_unit(unit_id="p1_bearing", status="open")],
            )
        ]
    )
    records = [_result_record(turn=5, outputs=_crop_outputs(aliases=["p1_bearing"]))]
    for status in ("ambiguous", "failed"):
        worklist = build_atom_evidence_worklist(
            resolution_state=state,
            recent_result_records=records,
            delegate_result_records=[
                _delegate_record(
                    turn=6,
                    alias="p1_bearing",
                    status=status,
                    context_refs=["image:derived:crop-p1_bearing"],
                )
            ],
        )
        atom = _atom(worklist, "p1_bearing")
        assert atom["status"] == "open"
        assert atom["utilization_status"] == "open_packet_used_not_determined"
        assert atom["delegate_refs"][0]["delegate_status"] == status


def test_closed_atom_with_evidence_refs_is_closed_evidence_referenced() -> None:
    crop_ref = "image:derived:crop-p1_closed"
    delegate_ref = "subtask:turn8:p1_closed"
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1",
                units=[
                    _unit(
                        unit_id="p1_closed",
                        status="closed",
                        determination="earned",
                        determined_value="42 ft",
                        evidence_refs=[crop_ref, delegate_ref],
                    )
                ],
            )
        ]
    )
    records = [_result_record(turn=6, outputs=_crop_outputs(aliases=["p1_closed"]))]
    delegates = [
        _delegate_record(
            turn=8,
            alias="p1_closed",
            context_refs=[crop_ref],
        )
    ]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
        delegate_result_records=delegates,
    )
    atom = _atom(worklist, "p1_closed")
    assert atom["utilization_status"] == "closed_evidence_referenced"
    assert atom["packet_refs"]
    assert atom["delegate_refs"] or any(p.get("delegate_refs") for p in atom["packet_refs"])


def test_shared_evidence_ref_when_crop_alias_differs() -> None:
    crop_ref = "image:derived:crop-p1_other"
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1",
                units=[
                    _unit(
                        unit_id="p1_acreage",
                        evidence_refs=[crop_ref],
                    )
                ],
            )
        ]
    )
    records = [_result_record(turn=6, outputs=_crop_outputs(aliases=["p1_other"]))]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    atom = _atom(worklist, "p1_acreage")
    assert atom["packet_refs"][0]["match_kind"] == "shared_evidence_ref"
    assert atom["utilization_status"] == "open_evidence_referenced_not_determined"


def test_unmatched_crop_alias_without_state_citation() -> None:
    state = _resolution_state(
        items=[_group_item(item_id="parcel_1", units=[_unit(unit_id="p1_known")])]
    )
    records = [
        _result_record(
            turn=6,
            outputs=_crop_outputs(aliases=["p1_known", "p1_orphan"]),
        )
    ]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    assert len(worklist["unmatched_packet_refs"]) == 1
    assert worklist["unmatched_packet_refs"][0]["source_alias"] == "p1_orphan"
    assert worklist["counts"]["unmatched_packet_refs"] == 1


def test_unmatched_crop_with_delegate_context_stays_visible() -> None:
    crop_ref = "image:derived:crop-p1_mismatch"
    state = _resolution_state(
        items=[_group_item(item_id="parcel_1", units=[_unit(unit_id="p1_known")])]
    )
    records = [
        _result_record(
            turn=6,
            outputs=_crop_outputs(aliases=["p1_known", "p1_mismatch"]),
        )
    ]
    delegates = [
        _delegate_record(
            turn=7,
            alias="read_mismatch_crop",
            status="ambiguous",
            context_refs=[crop_ref],
        )
    ]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
        delegate_result_records=delegates,
    )
    unmatched = worklist["unmatched_packet_refs"]
    assert len(unmatched) == 1
    row = unmatched[0]
    assert row["source_alias"] == "p1_mismatch"
    assert row["crop_ref"] == crop_ref
    assert row["delegate_refs"][0]["delegate_alias"] == "read_mismatch_crop"
    assert row["delegate_refs"][0]["delegate_status"] == "ambiguous"
    assert _atom(worklist, "p1_known")["utilization_status"] == "open_packet_ready_unused"
    assert _atom(worklist, "p1_known")["delegate_refs"] == []


def test_no_fuzzy_alias_matching() -> None:
    state = _resolution_state(
        items=[_group_item(item_id="parcel_1", units=[_unit(unit_id="p1_acreage")])]
    )
    records = [_result_record(turn=6, outputs=_crop_outputs(aliases=["p1_acreag"]))]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    atom = _atom(worklist, "p1_acreage")
    assert atom["utilization_status"] == "open_no_packet_seen"
    assert atom["packet_refs"] == []
    assert worklist["unmatched_packet_refs"][0]["source_alias"] == "p1_acreag"


def test_output_strips_sensitive_fields_and_respects_caps() -> None:
    aliases = [f"atom_{i}" for i in range(80)]
    state = _resolution_state(
        items=[_group_item(item_id="parcel_bulk", units=[_unit(unit_id=a) for a in aliases])]
    )
    records = [_result_record(turn=3, outputs=_crop_outputs(aliases=aliases[:20]))]
    worklist = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    serialized = json.dumps(worklist)
    assert "b64" not in serialized
    assert "raw_prompt_text" not in serialized
    assert "C:\\\\secret" not in serialized
    assert "C:\\secret" not in serialized
    assert len(worklist["atoms"]) <= 64

    summary = project_point_crop_set_summary(_crop_outputs(aliases=["x"]))
    assert summary is not None
    prebuilt = _result_record(turn=1, outputs={})
    prebuilt["point_crop_set_summary"] = summary
    worklist2 = build_atom_evidence_worklist(
        resolution_state=_resolution_state(
            items=[_group_item(item_id="g", units=[_unit(unit_id="x")])]
        ),
        recent_result_records=[prebuilt],
    )
    assert _atom(worklist2, "x")["packet_refs"]
