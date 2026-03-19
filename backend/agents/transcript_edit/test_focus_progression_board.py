from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.decision_ledger_focus import choose_investigation_focus
from backend.agents.transcript_edit.focus_authority_policy import authority_rank_for_candidate
from backend.harness.work_board.contracts import new_work_board, work_board_item_dict


def _ledger_with_material_mapping_blocker() -> dict:
    cr = {
        "mapping_blocking": True,
        "operational_impact": "mapping_blocking",
        "required_information": "need proof",
        "scope_status": "in_target",
        "scope_proof": [],
        "resolution_options": ["candidate_a", "candidate_b"],
    }
    return {
        "items": [
            {
                "key": "range",
                "label": "Range",
                "state": "unknown",
                "blocking": True,
                "alternatives": [],
                "evidence_refs": [],
                "closure_requirement": dict(cr),
            }
        ],
        "scope_summaries": {},
        "source_completeness": "complete",
    }


def test_ledger_mapping_authority_wins_over_emergent() -> None:
    ledger = _ledger_with_material_mapping_blocker()
    em = work_board_item_dict(
        item_id="harness:emergent:111111111111",
        title="Emergent high materiality closure branch for mapping",
        kind="transcript_edit.scan_integrity",
        state="open",
        materiality="high",
        blocking_impact="mapping_blocking",
        resolution_condition="Confirm scan",
        evidence_refs=["x"],
        domain_payload={"harness_lifecycle": {"created_at_epoch": 999999, "last_event_at_epoch": 999999}},
    )
    wb = new_work_board(domain_projection="decision_ledger", items=[em])
    focus = choose_investigation_focus(ledger, work_board=wb)
    assert focus is not None
    assert focus.get("decision_key") == "range"
    assert focus.get("focus_target_kind") == "ledger_decision"
    fa = focus.get("focus_authority")
    assert isinstance(fa, dict)
    assert fa.get("mode") == "ledger_absolute_precedence"


def test_emergent_preferred_when_no_material_mapping_blocker_in_closure() -> None:
    ledger = {
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
    em = work_board_item_dict(
        item_id="harness:emergent:222222222222",
        title="Dedicated orientation branch for tie-bearing preservation work",
        kind="transcript_edit.orientation",
        state="open",
        materiality="high",
        blocking_impact="mapping_blocking",
        resolution_condition="Document contradiction",
        evidence_refs=["f"],
    )
    wb = new_work_board(domain_projection="decision_ledger", items=[em])
    focus = choose_investigation_focus(ledger, work_board=wb)
    assert focus is not None
    assert str(focus.get("decision_key") or "").startswith("harness:emergent:")
    assert focus.get("focus_target_kind") == "harness_emergent"
    fa = focus.get("focus_authority")
    assert isinstance(fa, dict)
    assert fa.get("mode") == "emergent_may_lead"


def test_authority_policy_ranks_align_with_choose_winner() -> None:
    """Emergent defer rank is strictly after material ledger mapping blocker when mode is ledger_absolute."""
    ledger = _ledger_with_material_mapping_blocker()
    row = work_board_item_dict(
        item_id="harness:emergent:999999999999",
        title="Emergent competitor for authority rank check",
        kind="transcript_edit.scan_integrity",
        state="open",
        materiality="high",
        blocking_impact="mapping_blocking",
        resolution_condition="x",
        evidence_refs=["e"],
    )
    wb = new_work_board(domain_projection="decision_ledger", items=[row])
    focus = choose_investigation_focus(ledger, work_board=wb)
    assert focus and focus.get("decision_key") == "range"
    from backend.agents.transcript_edit.decision_ledger_closure import unresolved_mapping_blocking_requirements
    from backend.agents.transcript_edit.decision_ledger_scope import _ensure_ledger_shape

    norm = _ensure_ledger_shape(ledger)
    mbk = {
        str(i.get("key") or ""): i
        for i in unresolved_mapping_blocking_requirements(norm)
        if isinstance(i, dict)
    }
    emergent_c = {"_candidate_source": "harness_emergent", "key": "harness:emergent:999999999999"}
    ledger_range = {"_candidate_source": "ledger_decision", "key": "range"}
    assert authority_rank_for_candidate(emergent_c, mapping_blocking_by_key=mbk) > authority_rank_for_candidate(
        ledger_range,
        mapping_blocking_by_key=mbk,
    )
