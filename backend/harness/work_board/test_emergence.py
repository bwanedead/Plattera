from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger
from backend.harness.work_board.emergence import (
    apply_work_board_changes,
    evaluate_add_item_promotion,
    normalize_work_board_change,
)
from backend.harness.work_board.contracts import MAX_EMERGENT_PROPOSALS_PER_RESOLVER


def _add_proposal(**kwargs):  # type: ignore[no-untyped-def]
    base = {
        "op": "add_item",
        "title": "Explicit dependency branch for scan truncation check",
        "kind": "transcript_edit.investigation_branch",
        "reason": "Margin truncation may hide boundary call; durable board row preserves closure dependency.",
        "materiality": "high",
        "blocking_impact": "mapping_blocking",
        "resolution_condition": "Confirm full legal calls before mapping closure.",
        "dependencies": [],
        "evidence_refs": ["scan:edge_1"],
        "scope": {},
        "domain_payload": {},
    }
    base.update(kwargs)
    return base


def test_normalize_add_item_roundtrip() -> None:
    p = normalize_work_board_change(_add_proposal())
    assert p["op"] == "add_item"
    assert len(p["title"]) >= 8


def test_promotion_rejects_duplicate_ledger_decision_key() -> None:
    ledger = initialize_decision_ledger()
    items = [{"item_id": "te:ledger:range", "title": "Range", "domain_payload": {"decision_key": "range"}}]
    prop = _add_proposal(domain_payload={"decision_key": "range"})
    ok, code = evaluate_add_item_promotion(prop, ledger_decision_keys_set={"range"}, board_items=items)
    assert ok is False
    assert code == "duplicates_existing_ledger_decision"


def test_promotion_rejects_note_masquerading_as_item() -> None:
    ledger = initialize_decision_ledger()
    board = [{"item_id": "x", "title": "Other investigation"}]
    prop = _add_proposal(
        title="low signal title attempt longer",
        materiality="low",
        blocking_impact="quality_only",
        evidence_refs=["keep_signal"],
        dependencies=[],
        resolution_condition="no",
    )
    ok, code = evaluate_add_item_promotion(
        prop,
        ledger_decision_keys_set=set(),
        board_items=board,
    )
    assert ok is False
    assert code == "likely_note_not_item_use_attach_note"


def test_apply_accepts_add_and_attach_note() -> None:
    ledger = initialize_decision_ledger()
    projected = [
        {"item_id": "te:ledger:range", "title": "Range"},
    ]
    ch = [
        _add_proposal(
            title="Dedicated branch for OCR ambiguity cluster",
            kind="transcript_edit.ocr_cluster",
            reason="Operator reports repeated confusables; preserve as durable branch for closure path.",
            domain_payload={"cluster": "ocr"},
        ),
        normalize_work_board_change(
            {
                "op": "attach_note",
                "target_item_id": "te:ledger:range",
                "note": "Do not treat OCR hint as confirmed until image evidence lands.",
                "note_intent": "guardrail",
            }
        ),
    ]
    result = apply_work_board_changes(
        ch,
        decision_ledger=ledger,
        emergent_items=[],
        context_notes_by_item_id={},
        projected_ledgers_items=projected,
    )
    assert len(result["emergent_items"]) == 1
    assert str(result["emergent_items"][0].get("provenance") or "") == "harness.emergent.v1"
    assert "te:ledger:range" in result["context_notes_by_item_id"]
    notes = result["context_notes_by_item_id"]["te:ledger:range"]
    assert len(notes) == 1
    assert notes[0].get("non_canonical") is True


def test_apply_rejects_attach_unknown_id() -> None:
    ledger = initialize_decision_ledger()
    projected = [{"item_id": "te:ledger:range", "title": "Range"}]
    ch = [
        normalize_work_board_change(
            {
                "op": "attach_note",
                "target_item_id": "te:ledger:nonexistent",
                "note": "Nuance note that should fail.",
            }
        ),
    ]
    result = apply_work_board_changes(
        ch,
        decision_ledger=ledger,
        emergent_items=[],
        context_notes_by_item_id={},
        projected_ledgers_items=projected,
    )
    assert result["rejected"]
    assert not result["accepted"]


def test_normalize_list_respects_max() -> None:
    from backend.harness.work_board.emergence import normalize_work_board_changes_list

    raw = [_add_proposal(title=f"Title number {i} long enough" + "x" * 8, reason="y" * 30) for i in range(20)]
    out = normalize_work_board_changes_list(raw)
    assert len(out) == MAX_EMERGENT_PROPOSALS_PER_RESOLVER
