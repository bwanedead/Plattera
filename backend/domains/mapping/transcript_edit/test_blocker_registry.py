from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.blocker_registry import (
    apply_proposed_emergent_blocker_updates,
    blocker_health_snapshot,
    blocker_registry_delta,
    initialize_blocker_registry,
    link_prompt_to_blocker,
    mark_feedback_stale,
    mark_feedback_received,
    registry_snapshot_for_payload,
    select_primary_blocker,
    select_primary_blocker_with_reason,
    set_convention_context,
    supersede_prompt_link,
    sync_registry_from_ledger,
)
from backend.domains.mapping.transcript_edit.decision_ledger import initialize_decision_ledger_with_domain_template_seed


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
    ledger = initialize_decision_ledger_with_domain_template_seed()
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
    ledger = initialize_decision_ledger_with_domain_template_seed()
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
    ledger = initialize_decision_ledger_with_domain_template_seed()
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
    ledger = initialize_decision_ledger_with_domain_template_seed()
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


def test_selection_priority_answered_unintegrated_beats_open_target_scope() -> None:
    registry = initialize_blocker_registry(
        run_id="run-priority-1",
        session_id="session-priority-1",
        source_transcript_ref="in-memory://source.json",
    )
    registry["rows"] = [
        {
            "blocker_id": "blocker:range",
            "decision_key": "range",
            "state": "open",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 1,
        },
        {
            "blocker_id": "blocker:section",
            "decision_key": "section",
            "state": "answered_unintegrated",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 2,
        },
    ]
    selected = select_primary_blocker_with_reason(registry)
    row = selected.get("row") if isinstance(selected.get("row"), dict) else {}
    assert str(row.get("decision_key") or "") == "section"
    assert str(selected.get("reason_code") or "") == "priority_answered_unintegrated"


def test_selection_priority_target_scope_open_beats_unknown_scope_open() -> None:
    registry = initialize_blocker_registry(
        run_id="run-priority-2",
        session_id="session-priority-2",
        source_transcript_ref="in-memory://source.json",
    )
    registry["rows"] = [
        {
            "blocker_id": "blocker:township",
            "decision_key": "township",
            "state": "open",
            "mapping_blocking": True,
            "scope_status": "unknown",
            "updated_at": 2,
        },
        {
            "blocker_id": "blocker:range",
            "decision_key": "range",
            "state": "open",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 1,
        },
    ]
    selected = select_primary_blocker_with_reason(registry)
    row = selected.get("row") if isinstance(selected.get("row"), dict) else {}
    assert str(row.get("decision_key") or "") == "range"
    assert str(selected.get("reason_code") or "") == "priority_open_target_scope_mapping_blocker"


def test_waiting_feedback_does_not_preempt_answered_unintegrated() -> None:
    registry = initialize_blocker_registry(
        run_id="run-priority-3",
        session_id="session-priority-3",
        source_transcript_ref="in-memory://source.json",
    )
    registry["rows"] = [
        {
            "blocker_id": "blocker:range",
            "decision_key": "range",
            "state": "waiting_feedback",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 5,
        },
        {
            "blocker_id": "blocker:section",
            "decision_key": "section",
            "state": "answered_unintegrated",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 1,
        },
    ]
    selected = select_primary_blocker_with_reason(registry)
    row = selected.get("row") if isinstance(selected.get("row"), dict) else {}
    assert str(row.get("decision_key") or "") == "section"


def test_stale_feedback_for_superseded_prompt_is_ignored() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    _set_unresolved_range_blocker(ledger)
    registry = sync_registry_from_ledger(
        registry=initialize_blocker_registry(
            run_id="run-stale",
            session_id="session-stale",
            source_transcript_ref="in-memory://source.json",
        ),
        decision_ledger=ledger,
    )
    registry = link_prompt_to_blocker(
        registry=registry,
        decision_key="range",
        prompt_id="hitl_range_new",
        ticket_id="hitl_range_new",
        reason="prompt_issued",
    )
    registry = mark_feedback_stale(
        registry=registry,
        decision_key="range",
        prompt_id="hitl_range_old",
        reason="superseded_prompt_reply",
    )
    row = select_primary_blocker(registry) or {}
    assert str(row.get("state") or "") == "waiting_feedback"
    assert str(row.get("feedback_status") or "") == "stale"
    assert str(row.get("last_transition_reason") or "") == "superseded_prompt_reply"


def test_blocker_delta_reports_state_transition_and_resolved_ids() -> None:
    before = initialize_blocker_registry(
        run_id="run-delta",
        session_id="session-delta",
        source_transcript_ref="in-memory://source.json",
    )
    before["rows"] = [
        {
            "blocker_id": "blocker:range",
            "decision_key": "range",
            "state": "answered_unintegrated",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 1,
        }
    ]
    before["active_blocker_id"] = "blocker:range"
    after = initialize_blocker_registry(
        run_id="run-delta",
        session_id="session-delta",
        source_transcript_ref="in-memory://source.json",
    )
    after["rows"] = [
        {
            "blocker_id": "blocker:range",
            "decision_key": "range",
            "state": "resolved",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 2,
        }
    ]
    delta = blocker_registry_delta(before_registry=before, after_registry=after)
    assert "blocker:range" in list(delta.get("resolved_blocker_ids") or [])
    transitions = [row for row in list(delta.get("state_transitions") or []) if isinstance(row, dict)]
    assert any(
        str(row.get("blocker_id") or "") == "blocker:range"
        and str(row.get("before_state") or "") == "answered_unintegrated"
        and str(row.get("after_state") or "") == "resolved"
        for row in transitions
    )


def test_blocker_health_snapshot_detects_registry_ledger_mismatch() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    _set_unresolved_range_blocker(ledger)
    registry = initialize_blocker_registry(
        run_id="run-health",
        session_id="session-health",
        source_transcript_ref="in-memory://source.json",
    )
    registry["rows"] = [
        {
            "blocker_id": "blocker:section",
            "decision_key": "section",
            "state": "open",
            "mapping_blocking": True,
            "scope_status": "in_target",
            "updated_at": 1,
        }
    ]
    health = blocker_health_snapshot(registry=registry, decision_ledger=ledger)
    assert bool(health.get("ledger_registry_mismatch")) is True
    assert "range" in list(health.get("mismatch_only_in_ledger") or [])


def test_registry_exposes_convention_menu_and_emergent_parallel_rows() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    _set_unresolved_range_blocker(ledger)
    registry = initialize_blocker_registry(
        run_id="run-emergent",
        session_id="session-emergent",
        source_transcript_ref="in-memory://source.json",
    )
    registry = set_convention_context(
        registry=registry,
        convention_context={
            "document_convention": "plss",
            "convention_confidence": 0.9,
            "convention_signals": [{"family": "plss", "signal": r"\brange\b"}],
            "menu_family_candidates": ["plss", "source_quality"],
        },
    )
    registry = sync_registry_from_ledger(
        registry=registry,
        decision_ledger=ledger,
    )
    snapshot = registry_snapshot_for_payload(registry)
    assert str((snapshot.get("convention_context") or {}).get("document_convention") or "") == "plss"
    menu = snapshot.get("archetype_menu") if isinstance(snapshot.get("archetype_menu"), dict) else {}
    assert isinstance(menu.get("archetypes"), list)
    emergent = snapshot.get("emergent") if isinstance(snapshot.get("emergent"), dict) else {}
    rows = [row for row in list(emergent.get("rows") or []) if isinstance(row, dict)]
    assert len(rows) >= 1
    range_row = next(
        (row for row in rows if str(row.get("legacy_decision_key") or "") == "range"),
        {},
    )
    assert str(range_row.get("blocking_class") or "") in {"mapping_blocking", "closure_blocking"}


def test_emergent_add_and_resolve_updates_are_applied_without_mutating_legacy_rows() -> None:
    ledger = initialize_decision_ledger_with_domain_template_seed()
    _set_unresolved_range_blocker(ledger)
    registry = sync_registry_from_ledger(
        registry=initialize_blocker_registry(
            run_id="run-propose",
            session_id="session-propose",
            source_transcript_ref="in-memory://source.json",
        ),
        decision_ledger=ledger,
    )
    legacy_row_count = len([row for row in list((registry.get("rows") or [])) if isinstance(row, dict)])
    add_result = apply_proposed_emergent_blocker_updates(
        registry=registry,
        blocker_updates=[
            {
                "operation": "add",
                "blocker_kind": "custom:scan_smudge",
                "title": "Smudge On Range Token",
                "blocking_class": "source_blocking",
                "reason": "Ink smudge obscures one digit.",
                "scope_status": "in_target",
            }
        ],
        fallback_decision_key="range",
    )
    updated_registry = add_result["registry"]
    assert len(list(add_result.get("accepted") or [])) == 1
    emergent_rows = [row for row in list(((updated_registry.get("emergent") or {}).get("rows") or [])) if isinstance(row, dict)]
    added = next((row for row in emergent_rows if str(row.get("title") or "") == "Smudge On Range Token"), {})
    assert str(added.get("state") or "") == "open"
    resolve_result = apply_proposed_emergent_blocker_updates(
        registry=updated_registry,
        blocker_updates=[
            {
                "operation": "resolve",
                "blocker_id": str(added.get("blocker_id") or ""),
                "reason": "Operator provided clearer scan.",
            }
        ],
        fallback_decision_key="range",
    )
    resolved_registry = resolve_result["registry"]
    assert len(list(resolve_result.get("accepted") or [])) == 1
    resolved_rows = [row for row in list(((resolved_registry.get("emergent") or {}).get("rows") or [])) if isinstance(row, dict)]
    resolved = next((row for row in resolved_rows if str(row.get("blocker_id") or "") == str(added.get("blocker_id") or "")), {})
    assert str(resolved.get("state") or "") == "resolved"
    assert len([row for row in list((resolved_registry.get("rows") or [])) if isinstance(row, dict)]) == legacy_row_count


def test_emergent_update_validation_rejects_invalid_blocking_class_and_bad_custom_kind() -> None:
    registry = initialize_blocker_registry(
        run_id="run-invalid",
        session_id="session-invalid",
        source_transcript_ref="in-memory://source.json",
    )
    result = apply_proposed_emergent_blocker_updates(
        registry=registry,
        blocker_updates=[
            {
                "operation": "add",
                "blocker_kind": "custom:ok_name",
                "title": "X",
                "blocking_class": "not_allowed",
                "reason": "x",
            },
            {
                "operation": "add",
                "blocker_kind": "custom:BAD SPACE",
                "title": "Y",
                "blocking_class": "mapping_blocking",
                "reason": "y",
            },
        ],
        fallback_decision_key="range",
    )
    rejected = [row for row in list(result.get("rejected") or []) if isinstance(row, dict)]
    reasons = {str(row.get("reason") or "") for row in rejected}
    assert "invalid_blocking_class_for_add" in reasons
    assert "invalid_custom_blocker_kind" in reasons


def test_emergent_update_missing_target_and_supersede_conflict_rejected() -> None:
    registry = initialize_blocker_registry(
        run_id="run-supersede",
        session_id="session-supersede",
        source_transcript_ref="in-memory://source.json",
    )
    seeded = apply_proposed_emergent_blocker_updates(
        registry=registry,
        blocker_updates=[
            {
                "operation": "add",
                "blocker_kind": "custom:first",
                "title": "First",
                "blocking_class": "mapping_blocking",
                "reason": "first",
            },
            {
                "operation": "add",
                "blocker_kind": "custom:second",
                "title": "Second",
                "blocking_class": "mapping_blocking",
                "reason": "second",
            },
            {
                "operation": "add",
                "blocker_kind": "custom:third",
                "title": "Third",
                "blocking_class": "mapping_blocking",
                "reason": "third",
            },
        ],
        fallback_decision_key="range",
    )["registry"]
    rows = [row for row in list(((seeded.get("emergent") or {}).get("rows") or [])) if isinstance(row, dict)]
    first = next(row for row in rows if str(row.get("title") or "") == "First")
    second = next(row for row in rows if str(row.get("title") or "") == "Second")
    third = next(row for row in rows if str(row.get("title") or "") == "Third")
    step1 = apply_proposed_emergent_blocker_updates(
        registry=seeded,
        blocker_updates=[
            {
                "operation": "supersede",
                "blocker_id": str(second.get("blocker_id") or ""),
                "supersedes_blocker_id": str(first.get("blocker_id") or ""),
                "reason": "second supersedes first",
            }
        ],
        fallback_decision_key="range",
    )["registry"]
    step2 = apply_proposed_emergent_blocker_updates(
        registry=step1,
        blocker_updates=[
            {
                "operation": "update",
                "blocker_id": "emergent:agent:missing:1",
                "reason": "nope",
            },
            {
                "operation": "supersede",
                "blocker_id": str(third.get("blocker_id") or ""),
                "supersedes_blocker_id": str(first.get("blocker_id") or ""),
                "reason": "conflicting supersede",
            },
        ],
        fallback_decision_key="range",
    )
    rejected = [row for row in list(step2.get("rejected") or []) if isinstance(row, dict)]
    reasons = {str(row.get("reason") or "") for row in rejected}
    assert "update_target_blocker_not_found" in reasons
    assert "supersede_lineage_conflict" in reasons

