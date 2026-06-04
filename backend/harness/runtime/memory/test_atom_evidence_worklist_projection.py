"""Tests for atom evidence worklist prompt projection and compaction."""

from __future__ import annotations

import json

from harness.mission_state import new_resolution_state
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.atom_evidence_worklist_projection import (
    build_atom_evidence_worklist_for_prompt,
    compact_atom_evidence_worklist_for_prompt,
    project_atom_evidence_worklist_for_prompt,
)
from harness.runtime.memory.continuity_journal import build_kernel_step_result_record
from harness.runtime.memory.test_atom_evidence_worklist import (
    _crop_outputs,
    _delegate_record,
    _group_item,
    _resolution_state,
    _result_record,
    _unit,
)
from harness.runtime.orchestration.loop_health_summary import build_prompt_observability_summary
from harness.runtime.orchestration.prompt_packet_builder import _compact_prompt_observability_summary


def test_prompt_observability_includes_worklist_for_unused_packet() -> None:
    aliases = ["p1_ready"]
    loop_memory = LoopMemoryState()
    loop_memory.continuity.resolution_state = new_resolution_state(
        items=[
            {
                "item_id": "parcel_1",
                "title": "Parcel 1",
                "kind": "group",
                "status": "open",
                "structure_kind": "group",
                "covered_units": [
                    {
                        "unit_id": alias,
                        "title": alias,
                        "status": "open",
                    }
                    for alias in aliases
                ],
            }
        ]
    )
    loop_memory.continuity.kernel_step_result_records = [
        _result_record(turn=6, outputs=_crop_outputs(aliases=aliases)),
    ]
    summary = build_prompt_observability_summary(loop_memory)
    worklist = summary.get("atom_evidence_worklist")
    assert isinstance(worklist, dict)
    assert worklist.get("counts", {}).get("packet_ready_unused") == 1
    assert worklist["priority_rows"][0]["utilization_status"] == "open_packet_ready_unused"


def test_priority_ordering_puts_packet_ready_before_used() -> None:
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1",
                units=[
                    _unit(unit_id="p1_used"),
                    _unit(unit_id="p1_ready"),
                ],
            )
        ]
    )
    records = [
        _result_record(
            turn=6,
            outputs=_crop_outputs(aliases=["p1_used", "p1_ready"]),
        )
    ]
    delegates = [
        _delegate_record(
            turn=7,
            alias="p1_used",
            context_refs=["image:derived:crop-p1_used"],
        )
    ]
    projected = build_atom_evidence_worklist_for_prompt(
        resolution_state=state,
        recent_result_records=records,
        delegate_result_records=delegates,
    )
    assert projected is not None
    statuses = [row["utilization_status"] for row in projected["priority_rows"]]
    assert statuses.index("open_packet_ready_unused") < statuses.index(
        "open_packet_used_not_determined"
    )


def test_projection_strips_paths_b64_and_raw_prompts() -> None:
    state = _resolution_state(
        items=[_group_item(item_id="parcel_1", units=[_unit(unit_id="p1_ready")])]
    )
    records = [_result_record(turn=6, outputs=_crop_outputs(aliases=["p1_ready"]))]
    projected = build_atom_evidence_worklist_for_prompt(
        resolution_state=state,
        recent_result_records=records,
    )
    serialized = json.dumps(projected)
    assert "b64" not in serialized
    assert "raw_prompt_text" not in serialized
    assert "C:\\secret" not in serialized


def test_compaction_keeps_counts_priority_rows_and_unmatched() -> None:
    full = {
        "kind": "atom_evidence_worklist",
        "counts": {"atoms_total": 3, "packet_ready_unused": 2},
        "priority_rows": [{"atom_id": "a", "utilization_status": "open_packet_ready_unused"}],
        "unmatched_packet_refs": [{"source_alias": "orphan", "crop_ref": "image:derived:x"}],
        "atoms": [{"atom_id": "drop_me"}],
    }
    compact = compact_atom_evidence_worklist_for_prompt(full)
    assert compact is not None
    assert compact["counts"]["packet_ready_unused"] == 2
    assert compact["priority_rows"][0]["atom_id"] == "a"
    assert compact["unmatched_packet_refs"][0]["source_alias"] == "orphan"
    assert "atoms" not in compact

    summary = {
        "resolution_item_count": 1,
        "atom_evidence_worklist": full,
        "performance_evaluation": {"schema_version": 1},
    }
    prompt_compact = _compact_prompt_observability_summary(summary)
    block = prompt_compact["atom_evidence_worklist"]
    assert block["counts"]["packet_ready_unused"] == 2
    assert block["priority_rows"]
    assert "atoms" not in block


def test_project_drops_closed_atoms_from_priority_rows() -> None:
    state = _resolution_state(
        items=[
            _group_item(
                item_id="parcel_1",
                units=[
                    _unit(unit_id="p1_closed", status="closed", determination="earned"),
                    _unit(unit_id="p1_open"),
                ],
            )
        ]
    )
    records = [
        _result_record(turn=6, outputs=_crop_outputs(aliases=["p1_closed", "p1_open"])),
    ]
    from harness.runtime.memory.atom_evidence_worklist import build_atom_evidence_worklist

    full = build_atom_evidence_worklist(
        resolution_state=state,
        recent_result_records=records,
    )
    projected = project_atom_evidence_worklist_for_prompt(full)
    assert projected is not None
    ids = [row["atom_id"] for row in projected.get("priority_rows", [])]
    assert "p1_closed" not in ids
    assert "p1_open" in ids
