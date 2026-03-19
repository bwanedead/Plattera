from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.focus_authority_policy import (
    authority_rank_for_candidate,
    focus_authority_audit,
    resolve_focus_authority_mode,
)


def test_mode_emergent_may_lead_when_no_material_blockers() -> None:
    assert resolve_focus_authority_mode(mapping_blocking_by_key={}) == "emergent_may_lead"


def test_mode_ledger_absolute_when_blockers() -> None:
    assert resolve_focus_authority_mode(mapping_blocking_by_key={"range": {"mapping_blocking": True}}) == "ledger_absolute_precedence"


def test_rank_matches_phase5_semantics() -> None:
    mbk = {"range": {"mapping_blocking": True}}
    ledger_auth = {
        "_candidate_source": "ledger_decision",
        "key": "range",
    }
    ledger_other = {
        "_candidate_source": "ledger_decision",
        "key": "section",
    }
    emergent = {"_candidate_source": "harness_emergent", "key": "harness:emergent:abc"}
    assert authority_rank_for_candidate(ledger_auth, mapping_blocking_by_key=mbk) == 0
    assert authority_rank_for_candidate(ledger_other, mapping_blocking_by_key=mbk) == 1
    assert authority_rank_for_candidate(emergent, mapping_blocking_by_key=mbk) == 2
    assert authority_rank_for_candidate(emergent, mapping_blocking_by_key={}) == 0
    assert authority_rank_for_candidate(ledger_other, mapping_blocking_by_key={}) == 1


def test_focus_authority_audit_includes_mode_and_counts() -> None:
    mbk = {"range": {"mapping_blocking": True}}
    a = focus_authority_audit(mapping_blocking_by_key=mbk)
    assert a.get("mode") == "ledger_absolute_precedence"
    assert a.get("material_mapping_blocker_key_count") == 1
    assert "policy_summary" in a
