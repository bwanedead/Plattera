from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState
from backend.agents.transcript_edit.planner import _coerce_focus_move
from backend.agents.transcript_edit.work_board_runtime import apply_work_board_changes_from_resolver
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.harness.work_board.contracts import WORK_BOARD_VERSION, new_work_board, work_board_item_dict


def test_coerce_propose_work_board_changes() -> None:
    raw = {
        "decision_key": "range",
        "move": "propose_work_board_changes",
        "reason": "Organize durable branch",
        "iteration_summary": "Add board row",
        "work_board_changes": [
            {
                "op": "add_item",
                "title": "Scan truncation may hide boundary call text",
                "kind": "transcript_edit.scan_integrity",
                "reason": "Right margin crop visible; preserve explicit dependency for mapping closure work.",
                "materiality": "high",
                "blocking_impact": "mapping_blocking",
                "resolution_condition": "Need clearer scan page or confirm call from alternate source.",
                "evidence_refs": ["img:margin"],
                "dependencies": [],
                "scope": {},
                "domain_payload": {"note": "hint only"},
            }
        ],
    }
    out = _coerce_focus_move(
        parsed=raw,
        decision_key="range",
        source_transcript_ref="ref",
        source_transcript_hash="hash",
    )
    assert out["move"] == "propose_work_board_changes"
    assert isinstance(out.get("work_board_changes"), list) and len(out["work_board_changes"]) == 1


def test_runtime_apply_visible_in_focus_packet_and_composite_board() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    state = TranscriptEditLoopState(decision_ledger=ledger)
    changes = _coerce_focus_move(
        parsed={
            "decision_key": "range",
            "move": "propose_work_board_changes",
            "reason": "r",
            "iteration_summary": "s",
            "work_board_changes": [
                {
                    "op": "add_item",
                    "title": "Orientation gap on tie-bearing preservation",
                    "kind": "transcript_edit.orientation",
                    "reason": "Loop risks losing tie-bearing contradiction context across iterations without a durable row.",
                    "materiality": "high",
                    "blocking_impact": "mapping_blocking",
                    "resolution_condition": "Document contradiction or confirm single bearing.",
                    "evidence_refs": ["f:tie"],
                    "dependencies": [],
                    "scope": {},
                    "domain_payload": {},
                }
            ],
        },
        decision_key="range",
        source_transcript_ref="ref",
        source_transcript_hash="h",
    ).get("work_board_changes") or []

    apply_work_board_changes_from_resolver(
        state=state,
        decision_ledger=ledger,
        work_board_changes=[dict(x) for x in changes if isinstance(x, dict)],
    )
    packet = build_focus_packet(
        decision_ledger=ledger,
        decision_key="range",
        source_transcript_ref="ref",
        source_transcript_hash="h",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
        harness_emergent_board_items=state.harness_emergent_board_items,
        harness_board_context_notes=state.harness_board_context_notes,
    )
    wb = packet.get("work_board")
    assert isinstance(wb, dict)
    assert wb.get("schema_version") == WORK_BOARD_VERSION
    ids = {str(r.get("item_id")) for r in wb.get("items") or [] if isinstance(r, dict)}
    assert any(x.startswith("harness:emergent:") for x in ids)


def test_prompt_payload_includes_work_board_emergence_doctrine() -> None:
    from backend.agents.transcript_edit.prompting import build_focus_resolver_user_message

    msg = build_focus_resolver_user_message(
        focus_packet={
            "decision_key": "range",
            "source_transcript_ref": "r",
            "source_transcript_hash": "h",
        }
    )
    payload = json.loads(msg)
    assert "propose_work_board_changes" in (payload.get("allowed_moves") or [])
    sec = payload.get("work_board_emergence")
    assert isinstance(sec, dict)
    assert "doctrine" in sec
    assert isinstance(sec.get("transcript_edit_hints"), list)
    assert len(sec["transcript_edit_hints"]) >= 1


def test_choose_investigation_focus_selects_emergent_when_no_unresolved_ledger_candidates() -> None:
    ledger = {
        "items": [
            {
                "key": "range",
                "label": "Range westerly",
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
    row = work_board_item_dict(
        item_id="harness:emergent:beefcafe0001",
        title="Dedicated scan integrity closure branch for the mapping pipeline",
        kind="transcript_edit.scan_integrity",
        state="open",
        materiality="high",
        blocking_impact="mapping_blocking",
        resolution_condition="Confirm edge",
        evidence_refs=["e1"],
    )
    wb = new_work_board(domain_projection="decision_ledger", items=[row])
    focus = choose_investigation_focus(ledger, work_board=wb)
    assert focus is not None
    assert focus.get("focus_target_kind") == "harness_emergent"
    assert str(focus.get("decision_key") or "").startswith("harness:emergent:")


def test_harness_emergence_has_no_transcript_edit_imports() -> None:
    from pathlib import Path as P

    text = (P(__file__).resolve().parents[3] / "backend" / "harness" / "work_board" / "emergence.py").read_text(
        encoding="utf-8"
    )
    assert "transcript_edit" not in text
    assert "agents." not in text
