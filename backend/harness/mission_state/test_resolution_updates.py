from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed
from backend.harness.mission_state import (
    MAX_EMERGENT_PROPOSALS_PER_RESOLVER,
    apply_resolution_changes,
    evaluate_add_item_promotion,
    normalize_resolution_change,
    normalize_resolution_changes_list,
)


def _add_proposal(**kwargs):  # type: ignore[no-untyped-def]
    base = {
        "op": "add_item",
        "title": "Explicit dependency branch for scan truncation check",
        "kind": "transcript_edit.investigation_branch",
        "reason": "Margin truncation may hide boundary call; durable board row preserves closure dependency.",
        "materiality": "high",
        "blocking_impact": "domain_owned_label",
        "resolution_condition": "Confirm full legal calls before mapping closure.",
        "dependencies": [],
        "evidence_refs": ["scan:edge_1"],
        "scope": {},
        "domain_payload": {},
    }
    base.update(kwargs)
    return base


def test_normalize_add_item_roundtrip() -> None:
    proposal = normalize_resolution_change(_add_proposal())
    assert proposal["op"] == "add_item"
    assert len(proposal["title"]) >= 8


def test_promotion_rejects_duplicate_ledger_decision_key() -> None:
    items = [{"item_id": "te:ledger:range", "title": "Range", "domain_payload": {"decision_key": "range"}}]
    proposal = _add_proposal(domain_payload={"decision_key": "range"})
    ok, code = evaluate_add_item_promotion(proposal, ledger_decision_keys_set={"range"}, board_items=items)
    assert ok is False
    assert code == "duplicates_existing_ledger_decision"


def test_promotion_rejects_note_masquerading_as_item() -> None:
    proposal = _add_proposal(
        title="low signal title attempt longer",
        materiality="low",
        blocking_impact="domain_owned_label",
        evidence_refs=["keep_signal"],
        dependencies=[],
        resolution_condition="no",
    )
    ok, code = evaluate_add_item_promotion(proposal, ledger_decision_keys_set=set(), board_items=[{"item_id": "x", "title": "Other investigation"}])
    assert ok is False
    assert code == "likely_note_not_item_use_attach_note"


def test_apply_accepts_add_and_attach_note() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    result = apply_resolution_changes(
        [
            _add_proposal(
                title="Dedicated branch for OCR ambiguity cluster",
                kind="transcript_edit.ocr_cluster",
                reason="Operator reports repeated confusables; preserve as durable branch for closure path.",
                domain_payload={"cluster": "ocr"},
            ),
            normalize_resolution_change(
                {
                    "op": "attach_note",
                    "target_item_id": "te:ledger:range",
                    "note": "Do not treat OCR hint as confirmed until image evidence lands.",
                    "note_intent": "guardrail",
                }
            ),
        ],
        decision_ledger=ledger,
        emergent_items=[],
        context_notes_by_item_id={},
        projected_ledgers_items=[{"item_id": "te:ledger:range", "title": "Range"}],
    )
    assert len(result["emergent_items"]) == 1
    assert str(result["emergent_items"][0].get("provenance") or "") == "harness.emergent.v1"
    assert "te:ledger:range" in result["context_notes_by_item_id"]
    assert len(result["context_notes_by_item_id"]["te:ledger:range"]) == 1


def test_apply_rejects_attach_unknown_id() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    result = apply_resolution_changes(
        [
            normalize_resolution_change(
                {
                    "op": "attach_note",
                    "target_item_id": "te:ledger:nonexistent",
                    "note": "Nuance note that should fail.",
                }
            ),
        ],
        decision_ledger=ledger,
        emergent_items=[],
        context_notes_by_item_id={},
        projected_ledgers_items=[{"item_id": "te:ledger:range", "title": "Range"}],
    )
    assert result["rejected"]
    assert not result["accepted"]


def test_normalize_list_respects_max() -> None:
    raw = [_add_proposal(title=f"Title number {i} long enough" + "x" * 8, reason="y" * 30) for i in range(20)]
    out = normalize_resolution_changes_list(raw)
    assert len(out) == MAX_EMERGENT_PROPOSALS_PER_RESOLVER


def test_promotion_does_not_use_blocking_impact_as_structural_signal() -> None:
    ok, code = evaluate_add_item_promotion(
        {
            "title": "Title long enough for minimum length rule",
            "kind": "generic.work_item",
            "reason": "Reason with sufficient substance for the harness minimum.",
            "materiality": "medium",
            "blocking_impact": "any_domain_owned_critical_label",
            "resolution_condition": "x",
            "dependencies": [],
            "evidence_refs": [],
            "priority": 50,
        },
        ledger_decision_keys_set=set(),
        board_items=[],
    )
    assert ok is False
    assert code == "missing_structural_signal_for_new_item"


def test_promotion_accepts_non_transcript_workflow_using_generic_signals_only() -> None:
    ok, code = evaluate_add_item_promotion(
        {
            "title": "Toaster slot calibration burn-in",
            "kind": "appliance.qa",
            "reason": "Operator batch shows drift; track as durable work until variance bounds met.",
            "materiality": "high",
            "resolution_condition": "Three consecutive runs within spec.",
            "dependencies": [],
            "evidence_refs": [],
            "priority": 55,
        },
        ledger_decision_keys_set=set(),
        board_items=[],
    )
    assert ok is True
    assert code == "ok"


def test_promotion_accepts_via_priority_urgency_without_blocking_impact() -> None:
    ok, code = evaluate_add_item_promotion(
        {
            "title": "Another title meeting minimum length",
            "kind": "ops.follow_up",
            "reason": "Enough substance in this reason field for harness rules to pass.",
            "materiality": "medium",
            "resolution_condition": "short",
            "dependencies": [],
            "evidence_refs": [],
            "priority": 72,
        },
        ledger_decision_keys_set=set(),
        board_items=[],
    )
    assert ok is True
    assert code == "ok"


def test_active_paths_no_longer_import_legacy_shared_packages() -> None:
    repo = Path(__file__).resolve().parents[3]
    paths = [
        repo / "backend" / "agents" / "transcript_edit" / "decision_ledger_adapter.py",
        repo / "backend" / "agents" / "transcript_edit" / "work_board_projection.py",
        repo / "backend" / "agents" / "transcript_edit" / "work_board_runtime.py",
        repo / "backend" / "agents" / "transcript_edit" / "planner.py",
        repo / "backend" / "agents" / "transcript_edit" / "emergent_lifecycle_runtime.py",
        repo / "backend" / "agents" / "transcript_edit" / "board_focus_shaping.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "harness.work_board" not in text
        assert "harness.decision_ledger" not in text
