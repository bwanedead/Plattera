from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.work_board_read import (
    board_dependencies,
    board_evidence_refs,
    board_state,
    generic_knowns_snapshot,
    ledger_board_parity,
)


def test_generic_knowns_has_no_deed_native_top_level_slots() -> None:
    item = {
        "item_id": "te:ledger:range",
        "state": "blocked",
        "materiality": "high",
        "blocking_impact": "mapping_blocking",
        "resolution_condition": "pick value",
        "evidence_refs": ["a"],
        "dependencies": ["d1"],
        "domain_payload": {"decision_key": "range"},
    }
    snap = generic_knowns_snapshot(item)
    assert snap is not None
    assert set(snap.keys()) <= {
        "item_id",
        "state",
        "materiality",
        "blocking_impact",
        "resolution_condition",
        "evidence_refs",
        "dependencies",
    }
    assert "township" not in snap


def test_ledger_board_parity_ok() -> None:
    board = {
        "item_id": "te:ledger:section",
        "blocking_impact": "mapping_blocking",
        "domain_payload": {"decision_key": "section"},
    }
    ledger = {
        "key": "section",
        "blocking": True,
        "closure_requirement": {"mapping_blocking": True},
    }
    p = ledger_board_parity("section", ledger, board)
    assert p["identity_aligned"] is True
    assert p["posture_aligned"] is True
    assert p["code"] == "ok"


def test_ledger_board_parity_posture_mismatch() -> None:
    board = {
        "item_id": "te:ledger:section",
        "blocking_impact": "quality_only",
        "domain_payload": {"decision_key": "section"},
    }
    ledger = {
        "key": "section",
        "blocking": True,
        "closure_requirement": {"mapping_blocking": True},
    }
    p = ledger_board_parity("section", ledger, board)
    assert p["identity_aligned"] is True
    assert p["posture_aligned"] is False
    assert p["code"] == "posture_mismatch"


def test_evidence_and_dependency_limits() -> None:
    item = {
        "evidence_refs": [f"r{i}" for i in range(30)],
        "dependencies": [f"d{i}" for i in range(30)],
    }
    assert len(board_evidence_refs(item, limit=5)) == 5
    assert len(board_dependencies(item, limit=3)) == 3


def test_board_state_normalizes() -> None:
    assert board_state({"state": "BLOCKED"}) == "blocked"

