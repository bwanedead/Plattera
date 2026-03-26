from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.focus_packet_board_context import build_work_board_focus_context_bundle
from backend.harness.work_board.contracts import new_work_board, work_board_item_dict


def test_bounded_notes_and_linked_hints_only() -> None:
    dep_id = "harness:emergent:bbbbbbbbbbbb"
    focused = work_board_item_dict(
        item_id="harness:emergent:aaaaaaaaaaaa",
        title="Focused item with notes",
        kind="k",
        state="open",
        materiality="high",
        blocking_impact="mapping_blocking",
        dependencies=[dep_id],
        evidence_refs=["e"],
        resolution_condition="rc",
        context_notes=[
            {"body": "n1 focused", "intent": "hint", "non_canonical": True},
            {"body": "n2 focused", "intent": None, "non_canonical": True},
        ],
        domain_payload={"harness_lifecycle": {"created_at_epoch": 100, "last_event_at_epoch": 100}},
    )
    other = work_board_item_dict(
        item_id=dep_id,
        title="Dependency row",
        kind="k",
        state="open",
        materiality="medium",
        blocking_impact="mapping_blocking",
        evidence_refs=[],
        resolution_condition=None,
        context_notes=[{"body": "linked only", "non_canonical": True}],
    )
    noise = work_board_item_dict(
        item_id="harness:emergent:cccccccccccc",
        title="Unrelated",
        kind="k",
        state="open",
        materiality="low",
        blocking_impact="quality_only",
        evidence_refs=[],
        context_notes=[{"body": "should not appear", "non_canonical": True}],
    )
    wb = new_work_board(domain_projection="t", items=[focused, other, noise])
    ctx = build_work_board_focus_context_bundle(
        decision_key="harness:emergent:aaaaaaaaaaaa",
        focus_target_kind="harness_emergent",
        active_work_item=dict(focused),
        work_board=wb,
        now_epoch=200,
    )
    assert len(ctx["focused_context_notes"]) == 2
    assert all(n.get("non_canonical") is True for n in ctx["focused_context_notes"])
    assert len(ctx["linked_context_note_hints"]) == 1
    assert ctx["linked_context_note_hints"][0]["item_id"] == dep_id
    assert "should not appear" not in str(ctx)


def test_focus_packet_execution_context_has_work_board_focus_context() -> None:
    row = work_board_item_dict(
        item_id="harness:emergent:dddddddddddd",
        title="Packet lifecycle visibility",
        kind="k",
        state="investigating",
        materiality="high",
        blocking_impact="mapping_blocking",
        evidence_refs=["e"],
        resolution_condition="Need clearer scan",
        context_notes=[{"body": "sticky", "non_canonical": True}],
    )
    ledger_no_material_blocker = {
        "items": [
            {
                "key": "range",
                "label": "Range",
                "state": "verified",
                "blocking": False,
                "alternatives": [],
                "evidence_refs": [],
                "closure_requirement": {"mapping_blocking": False, "scope_status": "in_target"},
            }
        ],
        "scope_summaries": {},
        "source_completeness": "complete",
    }
    packet = build_focus_packet(
        decision_ledger=ledger_no_material_blocker,
        decision_key="harness:emergent:dddddddddddd",
        source_transcript_ref="ref",
        source_transcript_hash="h",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
        harness_emergent_board_items=[dict(row)],
        harness_board_context_notes={},
    )
    ec = packet.get("execution_context") or {}
    wbc = ec.get("work_board_focus_context")
    assert isinstance(wbc, dict)
    assert wbc.get("schema_version") == "work_board_focus_context.v1"
    assert wbc.get("focus_target_kind") == "harness_emergent"
    assert wbc.get("board_item_id") == "harness:emergent:dddddddddddd"
    assert wbc.get("board_mapping_blocking_count") == 0
    assert (wbc.get("board_lifecycle") or {}).get("board_state") == "investigating"
    assert wbc.get("open_work_summary")
