from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.board_focus_shaping import board_focus_sort_suffix
from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.work_board_projection import (
    active_work_board_item_for_key,
    project_decision_ledger_to_work_board,
)


def _tie_pair_ledger() -> dict:
    cr: dict = {
        "block_reason": "ambiguity",
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "required_information": "r",
        "self_retrievable": "yes",
        "retrieval_attempted": False,
        "retrieval_blocker": None,
        "minimal_user_action": "act",
        "resolution_options": ["a"],
        "evidence_refs": [],
        "attempt_summary": "sum",
        "scope_status": "in_target",
        "scope_proof": [],
    }
    return {
        "items": [
            {
                "key": "z_tie_first",
                "label": "first",
                "state": "unknown",
                "blocking": True,
                "alternatives": [],
                "evidence_refs": [],
                "closure_requirement": dict(cr),
            },
            {
                "key": "z_tie_second",
                "label": "second",
                "state": "unknown",
                "blocking": True,
                "alternatives": [],
                "evidence_refs": [],
                "closure_requirement": dict(cr),
            },
        ],
        "scope_summaries": {},
        "source_completeness": "complete",
    }


def test_board_focus_sort_suffix_ignores_board_when_parity_bad() -> None:
    ledger_item = {
        "key": "k",
        "blocking": True,
        "closure_requirement": {"mapping_blocking": True},
    }
    board_item = {"domain_payload": {"decision_key": "k"}, "blocking_impact": "quality_only"}
    s = board_focus_sort_suffix("k", ledger_item, board_item)
    assert s == (1, 0, 0)


def test_board_focus_sort_suffix_prefers_high_materiality_when_parity_ok() -> None:
    ledger_item = {
        "key": "k",
        "blocking": True,
        "closure_requirement": {"mapping_blocking": True},
    }
    hi = {"domain_payload": {"decision_key": "k"}, "blocking_impact": "mapping_blocking", "materiality": "high", "state": "open"}
    lo = {"domain_payload": {"decision_key": "k"}, "blocking_impact": "mapping_blocking", "materiality": "low", "state": "open"}
    assert board_focus_sort_suffix("k", ledger_item, hi) < board_focus_sort_suffix("k", ledger_item, lo)


def test_choose_investigation_focus_board_tie_prefers_higher_materiality_when_parity_ok() -> None:
    ledger = _tie_pair_ledger()
    board = project_decision_ledger_to_work_board(ledger)
    row_second = active_work_board_item_for_key(board, "z_tie_second")
    assert isinstance(row_second, dict)
    row_second = dict(row_second)
    row_second["materiality"] = "low"
    new_items: list[dict] = []
    for it in list(board.get("items") or []):
        if isinstance(it, dict) and str(it.get("item_id")) == "te:ledger:z_tie_second":
            new_items.append(row_second)
        elif isinstance(it, dict):
            new_items.append(dict(it))
    board = {**board, "items": new_items}
    focus = choose_investigation_focus(ledger, work_board=board)
    assert focus is not None
    assert str(focus.get("decision_key")) == "z_tie_first"


def test_choose_investigation_focus_posture_mismatch_does_not_promote_board_favorite() -> None:
    ledger = _tie_pair_ledger()
    board = project_decision_ledger_to_work_board(ledger)
    row_second = active_work_board_item_for_key(board, "z_tie_second")
    assert isinstance(row_second, dict)
    row_second = dict(row_second)
    row_second["blocking_impact"] = "quality_only"
    row_second["materiality"] = "low"
    new_items: list[dict] = []
    for it in list(board.get("items") or []):
        if isinstance(it, dict) and str(it.get("item_id")) == "te:ledger:z_tie_second":
            new_items.append(row_second)
        elif isinstance(it, dict):
            new_items.append(dict(it))
    board = {**board, "items": new_items}
    focus = choose_investigation_focus(ledger, work_board=board)
    assert focus is not None
    assert str(focus.get("decision_key")) == "z_tie_first"
