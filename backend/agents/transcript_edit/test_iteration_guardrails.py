from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.iteration_pipeline import (
    _accept_apply_edit_plan,
    _findings_for_focus_key,
    _accept_mark_blocked,
    _accept_mark_resolved_no_edit,
    _select_focus_decision_key,
)


def _ledger_item(*, key: str, state: str, mapping_blocking: bool = True, block_reason: str = "ambiguity") -> dict:
    return {
        "key": key,
        "state": state,
        "blocking": mapping_blocking,
        "closure_requirement": {
            "mapping_blocking": mapping_blocking,
            "block_reason": block_reason,
            "resolution_options": ["x"],
            "evidence_refs": ["test"],
        },
    }


def test_select_focus_decision_key_prioritizes_feedback_item_when_unresolved() -> None:
    ledger = {"items": [_ledger_item(key="range", state="disputed"), _ledger_item(key="section", state="disputed")]}
    selected = _select_focus_decision_key(
        decision_ledger=ledger,
        fallback_focus={"decision_key": "range"},
        focus_feedback={"decision_key": "section", "selected_value": "Section 12"},
    )
    assert selected == "section"


def test_mark_resolved_no_edit_acceptance_requires_deterministic_resolution() -> None:
    unresolved_ledger = {"items": [_ledger_item(key="range", state="candidate_found")]}
    resolved_ledger = {"items": [_ledger_item(key="range", state="verified")]}
    assert _accept_mark_resolved_no_edit(decision_ledger=unresolved_ledger, decision_key="range") is False
    assert _accept_mark_resolved_no_edit(decision_ledger=resolved_ledger, decision_key="range") is True


def test_mark_blocked_accepts_dependency_case_and_rejects_generic_case() -> None:
    dependency_ledger = {"items": [_ledger_item(key="range", state="disputed", block_reason="dependency")]}
    generic_ledger = {"items": [_ledger_item(key="range", state="disputed", block_reason="ambiguity")]}
    assert (
        _accept_mark_blocked(
            decision_ledger=dependency_ledger,
            decision_key="range",
            resolver_reason="cannot_continue",
            hitl_enabled=True,
        )
        is True
    )
    assert (
        _accept_mark_blocked(
            decision_ledger=generic_ledger,
            decision_key="range",
            resolver_reason="cannot_continue",
            hitl_enabled=True,
        )
        is False
    )


def test_apply_edit_plan_acceptance_requires_focus_scope_and_ops() -> None:
    good_plan = {"ops": [{"op_id": "op-1"}]}
    bad_plan = {"ops": []}
    assert _accept_apply_edit_plan(resolver_decision_key="range", focus_key="range", plan_payload=good_plan) is True
    assert _accept_apply_edit_plan(resolver_decision_key="section", focus_key="range", plan_payload=good_plan) is False
    assert _accept_apply_edit_plan(resolver_decision_key="range", focus_key="range", plan_payload=bad_plan) is False


def test_findings_for_focus_key_preserves_range_identity_over_generic_plss() -> None:
    findings = [
        {
            "finding_id": "plss_range_conflict_001",
            "finding_type": "plss_consistency",
            "message": "PLSS contradiction between Range 75 West and Range 74 West.",
        },
        {
            "finding_id": "plss_township_conflict_001",
            "finding_type": "plss_consistency",
            "message": "Township token mismatch.",
        },
    ]
    focused_range = _findings_for_focus_key(top_findings=findings, focus_key="range")
    assert len(focused_range) == 1
    assert str(focused_range[0].get("finding_id") or "") == "plss_range_conflict_001"


def test_select_focus_decision_key_does_not_prioritize_outside_scope_feedback() -> None:
    ledger = {
        "items": [
            _ledger_item(key="range", state="disputed"),
            _ledger_item(key="section", state="disputed"),
        ]
    }
    ledger["items"][0]["scope_id"] = "target_scope"
    ledger["items"][0]["in_target_scope"] = True
    ledger["items"][1]["scope_id"] = "outside_target_scope"
    ledger["items"][1]["in_target_scope"] = False
    ledger["items"][1]["closure_requirement"]["scope_status"] = "outside_target"
    ledger["items"][1]["closure_requirement"]["scope_proof"] = ["explicit_outside_target_text"]
    selected = _select_focus_decision_key(
        decision_ledger=ledger,
        fallback_focus={"decision_key": "range"},
        focus_feedback={"decision_key": "section", "selected_value": "Section 12"},
    )
    assert selected == "range"
