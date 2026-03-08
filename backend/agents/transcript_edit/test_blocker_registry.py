from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.blocker_registry import (
    initialize_blocker_registry,
    link_prompt_to_blocker,
    mark_feedback_received,
    registry_snapshot_for_payload,
    select_primary_blocker,
    supersede_prompt_link,
    sync_registry_from_ledger,
)
from backend.agents.transcript_edit.decision_ledger import initialize_decision_ledger


def _set_unresolved_range_blocker(ledger: dict) -> None:
    items = ledger.get("items") if isinstance(ledger.get("items"), list) else []
    for item in items:
        if not isinstance(item, dict):
            continue
        if str(item.get("key") or "") == "range":
            item["state"] = "disputed"
            item["blocking"] = True
            item["scope_id"] = "target_scope"
            item["in_target_scope"] = True
            item["closure_requirement"] = {
                "mapping_blocking": True,
                "scope_status": "in_target",
                "scope_proof": [],
                "block_reason": "ambiguity",
                "required_information": "Confirm exact range token.",
                "minimal_user_action": "Pick Range 74 or 75.",
                "attempt_summary": "Conflicting range tokens remain.",
            }
            continue
        item["state"] = "verified"
        item["blocking"] = False
        item["closure_requirement"] = None


def test_registry_creation_from_unresolved_ledger_items() -> None:
    ledger = initialize_decision_ledger()
    _set_unresolved_range_blocker(ledger)
    registry = initialize_blocker_registry(
        run_id="tx-agent-run-1",
        session_id="session-1",
        source_transcript_ref="in-memory://source.json",
    )
    registry = sync_registry_from_ledger(
        registry=registry,
        decision_ledger=ledger,
        run_id="tx-agent-run-1",
        session_id="session-1",
        source_transcript_ref="in-memory://source.json",
    )
    snapshot = registry_snapshot_for_payload(registry)
    rows = [row for row in list(snapshot.get("rows") or []) if isinstance(row, dict)]
    assert len(rows) >= 1
    row = next(item for item in rows if str(item.get("decision_key") or "") == "range")
    assert str(row.get("state") or "") == "open"
    assert str(row.get("scope_status") or "") == "in_target"
    assert bool(row.get("mapping_blocking")) is True
    assert int((snapshot.get("counts") or {}).get("open") or 0) >= 1


def test_registry_hitl_linkage_and_feedback_transition() -> None:
    ledger = initialize_decision_ledger()
    _set_unresolved_range_blocker(ledger)
    registry = sync_registry_from_ledger(
        registry=initialize_blocker_registry(
            run_id="tx-agent-run-2",
            session_id="session-2",
            source_transcript_ref="in-memory://source.json",
        ),
        decision_ledger=ledger,
    )
    registry = link_prompt_to_blocker(
        registry=registry,
        decision_key="range",
        prompt_id="hitl_range_1_resolver",
        ticket_id="hitl_range_1_resolver",
        reason="resolver_requested_feedback",
    )
    row = select_primary_blocker(registry) or {}
    assert str(row.get("decision_key") or "") == "range"
    assert str(row.get("state") or "") == "waiting_feedback"
    registry = mark_feedback_received(
        registry=registry,
        decision_key="range",
        prompt_id="hitl_range_1_resolver",
        feedback_value="Range 75 West",
        feedback_note="Operator confirmed range 75.",
        reason="feedback_consumed",
    )
    row2 = select_primary_blocker(registry) or {}
    assert str(row2.get("state") or "") == "answered_unintegrated"
    assert str(row2.get("feedback_status") or "") == "received"
    assert str(row2.get("feedback_value") or "") == "Range 75 West"


def test_registry_supersede_prompt_marks_old_state_and_reissues_waiting() -> None:
    ledger = initialize_decision_ledger()
    _set_unresolved_range_blocker(ledger)
    registry = sync_registry_from_ledger(
        registry=initialize_blocker_registry(
            run_id="tx-agent-run-3",
            session_id="session-3",
            source_transcript_ref="in-memory://source.json",
        ),
        decision_ledger=ledger,
    )
    registry = link_prompt_to_blocker(
        registry=registry,
        decision_key="range",
        prompt_id="hitl_range_1_old",
        ticket_id="hitl_range_1_old",
        reason="initial_prompt",
    )
    registry = supersede_prompt_link(
        registry=registry,
        decision_key="range",
        old_prompt_id="hitl_range_1_old",
        new_prompt_id="hitl_range_2_new",
        reason="reason_changed_reissue",
    )
    primary = select_primary_blocker(registry) or {}
    assert str(primary.get("state") or "") == "waiting_feedback"
    assert str(primary.get("linked_prompt_id") or "") == "hitl_range_2_new"


def test_waiting_feedback_row_does_not_advertise_integrate_feedback_action() -> None:
    ledger = initialize_decision_ledger()
    _set_unresolved_range_blocker(ledger)
    registry = sync_registry_from_ledger(
        registry=initialize_blocker_registry(
            run_id="tx-agent-run-4",
            session_id="session-4",
            source_transcript_ref="in-memory://source.json",
        ),
        decision_ledger=ledger,
    )
    registry = link_prompt_to_blocker(
        registry=registry,
        decision_key="range",
        prompt_id="hitl_range_5_waiting",
        ticket_id="hitl_range_5_waiting",
        reason="resolver_requested_feedback",
    )
    primary = select_primary_blocker(registry) or {}
    assert str(primary.get("state") or "") == "waiting_feedback"
    actions = [str(v) for v in list(primary.get("next_valid_actions") or [])]
    assert "integrate_feedback" not in actions
