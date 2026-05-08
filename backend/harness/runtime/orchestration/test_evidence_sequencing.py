"""Tests for evidence_sequencing.py — earned-before-claim-local-evidence debt detection.

Regression shapes match the run-16 turn-23/25 sequence:
  - Turn 23: unit earned/closed with determined_value, no locators → new debt
  - Turn 25: locator added post-hoc to that unit → posthoc_recheck_needed
  - Later turn: verification_basis or determined_value updated → cleared from posthoc debt
"""

from __future__ import annotations

import pytest

from harness.mission_state import (
    EvidenceLocator,
    ResolutionCoveredUnit,
    ResolutionItem,
    new_resolution_state,
)
from harness.runtime.orchestration.evidence_sequencing import (
    _is_earned_exact,
    _has_locators,
    _unit_key,
    apply_sequencing_debt_from_patch,
    detect_sequencing_debts,
)
from harness.runtime.memory.loop_state import LoopMemoryState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _locator(ref_id: str = "some:ref", *, locator_kind: str = "image_region") -> EvidenceLocator:
    return EvidenceLocator(
        ref_id=ref_id,
        locator_kind=locator_kind,
        box_norm=[0.1, 0.1, 0.2, 0.2],
    )


def _unit(
    unit_id: str,
    *,
    status: str = "closed",
    determination: str | None = "earned",
    determined_value: str | None = "42",
    verification_basis: str | None = None,
    locators: list[EvidenceLocator] | None = None,
) -> ResolutionCoveredUnit:
    return ResolutionCoveredUnit(
        unit_id=unit_id,
        title=f"Unit {unit_id}",
        status=status,
        determination=determination,
        determined_value=determined_value,
        verification_basis=verification_basis,
        evidence_locators=locators or [],
    )


def _item(item_id: str, *, units: list[ResolutionCoveredUnit] | None = None) -> ResolutionItem:
    return ResolutionItem(
        item_id=item_id,
        title=f"Item {item_id}",
        kind="atomic",
        status="open",
        covered_units=units or [],
    )


def _rs(items: list[ResolutionItem]):
    rs = new_resolution_state()
    return rs.model_copy(update={"items": items})


# ---------------------------------------------------------------------------
# _is_earned_exact
# ---------------------------------------------------------------------------

def test_is_earned_exact_true_for_closed_with_value() -> None:
    u = _unit("u1", status="closed", determined_value="answer")
    assert _is_earned_exact(u) is True


def test_is_earned_exact_true_for_earned_determination_with_value() -> None:
    u = _unit("u1", status="in_progress", determination="earned", determined_value="x")
    assert _is_earned_exact(u) is True


def test_is_earned_exact_false_without_determined_value() -> None:
    u = _unit("u1", status="closed", determined_value=None)
    assert _is_earned_exact(u) is False


def test_is_earned_exact_false_for_open_status_without_earned_determination() -> None:
    u = _unit("u1", status="open", determination=None, determined_value="x")
    assert _is_earned_exact(u) is False


# ---------------------------------------------------------------------------
# _has_locators
# ---------------------------------------------------------------------------

def test_has_locators_true_when_locators_present() -> None:
    u = _unit("u1", locators=[_locator()])
    assert _has_locators(u) is True


def test_has_locators_false_when_empty() -> None:
    u = _unit("u1", locators=[])
    assert _has_locators(u) is False


# ---------------------------------------------------------------------------
# detect_sequencing_debts — run-16 regression
# ---------------------------------------------------------------------------

def test_detect_new_earned_debt_no_locators() -> None:
    """Turn-23 shape: unit becomes earned with determined_value but no locators → new debt."""
    before = _rs([_item("item1", units=[
        _unit("u1", status="open", determination=None, determined_value=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determination="earned", determined_value="Section 2"),
    ])])
    new_debt, new_posthoc, cleared, _ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={},
        existing_posthoc_debt={},
        iteration=23,
    )
    key = _unit_key("item1", "u1")
    assert key in new_debt, f"Expected debt for u1; got new_debt={new_debt}"
    assert new_debt[key] == 23
    assert not new_posthoc
    assert not cleared


def test_detect_no_debt_when_locator_exists_at_earn_time() -> None:
    """Unit becomes earned with locators already present — no debt."""
    before = _rs([_item("item1", units=[
        _unit("u1", status="open", determination=None, determined_value=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()]),
    ])])
    new_debt, new_posthoc, cleared, _ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={},
        existing_posthoc_debt={},
        iteration=10,
    )
    assert not new_debt, "Should not create debt when locators exist at earn time"


def test_detect_posthoc_when_locator_added_to_debt_unit() -> None:
    """Turn-25 shape: locator added to already-earned unit that has debt → posthoc_recheck."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="Section 2"),  # no locators
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="Section 2", locators=[_locator()]),
    ])])
    new_debt, new_posthoc, cleared, _ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={},
        iteration=25,
    )
    assert key in new_posthoc, f"Expected posthoc for u1; got new_posthoc={new_posthoc}"
    assert new_posthoc[key] == 25
    assert not cleared


def test_detect_no_posthoc_when_unit_not_in_debt() -> None:
    """Adding locators to a unit that was never in debt does not trigger posthoc."""
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()]),
    ])])
    _, new_posthoc, *_ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={},  # unit not in debt
        existing_posthoc_debt={},
        iteration=5,
    )
    assert not new_posthoc


def test_detect_clears_posthoc_when_verification_basis_updated() -> None:
    """Post-hoc debt is cleared when the agent updates verification_basis."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()], verification_basis=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()], verification_basis="Confirmed via field survey"),
    ])])
    _, new_posthoc, cleared, _ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={key: 25},
        iteration=30,
    )
    assert key in cleared, f"Expected u1 cleared from posthoc; got cleared={cleared}"
    assert key not in new_posthoc


def test_detect_clears_posthoc_when_determined_value_changed() -> None:
    """Post-hoc debt cleared when determined_value is revised."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="old value"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="revised value"),
    ])])
    _, new_posthoc, cleared, _ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={key: 25},
        iteration=32,
    )
    assert key in cleared


def test_detect_clears_posthoc_when_status_reopened() -> None:
    """Post-hoc debt cleared when agent reopens/corrects the status."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="open", determination=None, determined_value="42"),
    ])])
    _, _, cleared, _ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={key: 25},
        iteration=33,
    )
    assert key in cleared


def test_detect_earned_debt_only_recorded_once() -> None:
    """Subsequent patches on an already-debted unit do not create duplicate debt."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", verification_basis="some text"),
    ])])
    new_debt, *_ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},  # already in debt
        existing_posthoc_debt={},
        iteration=26,
    )
    assert key not in new_debt, "Should not re-add debt for unit already in earned_debt"


def test_detect_posthoc_with_simultaneous_re_evaluation_not_flagged() -> None:
    """If the same patch that adds locators also updates verification_basis, no posthoc debt."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", verification_basis=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit(
            "u1",
            status="closed",
            determined_value="42",
            verification_basis="Re-verified via locator inspection",
            locators=[_locator()],
        ),
    ])])
    _, new_posthoc, *_ = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={},
        iteration=25,
    )
    assert key not in new_posthoc, "Simultaneous re-evaluation should not produce posthoc debt"


def test_detect_clears_earned_on_same_turn_locator_and_re_eval() -> None:
    """Same-turn locator + vb update on earned-only debt unit → cleared_earned, no posthoc."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", verification_basis=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit(
            "u1",
            status="closed",
            determined_value="42",
            verification_basis="Verified via locator",
            locators=[_locator()],
        ),
    ])])
    _, new_posthoc, cleared_posthoc, cleared_earned = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={},  # unit never entered posthoc stage
        iteration=24,
    )
    assert key not in new_posthoc, "Same-turn re-eval must not create posthoc debt"
    assert key not in cleared_posthoc, "cleared_posthoc must not include earned-only keys"
    assert key in cleared_earned, "Same-turn locator+re-eval must clear earned debt"


def test_detect_clears_earned_on_reopen_before_posthoc() -> None:
    """Reopen of an earned-only debt unit (before posthoc stage) clears earned debt."""
    key = _unit_key("item1", "u1")
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="open", determination=None, determined_value="42"),
    ])])
    _, _, cleared_posthoc, cleared_earned = detect_sequencing_debts(
        before, after,
        existing_earned_debt={key: 23},
        existing_posthoc_debt={},  # never entered posthoc
        iteration=26,
    )
    assert key not in cleared_posthoc, "cleared_posthoc must not include earned-only keys"
    assert key in cleared_earned, "Reopen of earned-only unit must clear earned debt"


# ---------------------------------------------------------------------------
# apply_sequencing_debt_from_patch — integration with LoopMemoryState
# ---------------------------------------------------------------------------

def test_apply_sequencing_debt_adds_to_continuity() -> None:
    """apply_sequencing_debt_from_patch must update earned_before_local_evidence_debt."""
    mem = LoopMemoryState()
    before = _rs([_item("item1", units=[
        _unit("u1", status="open", determined_value=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="answer"),
    ])])
    mem.continuity.resolution_state = after  # already applied
    apply_sequencing_debt_from_patch(mem, before_rs=before, after_rs=after, iteration=5)
    key = _unit_key("item1", "u1")
    assert key in mem.continuity.earned_before_local_evidence_debt
    assert mem.continuity.earned_before_local_evidence_debt[key] == 5


def test_apply_sequencing_debt_adds_posthoc_on_later_call() -> None:
    """Second call with locators → posthoc_recheck_needed_debt updated."""
    mem = LoopMemoryState()
    key = _unit_key("item1", "u1")
    mem.continuity.earned_before_local_evidence_debt = {key: 23}

    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42"),  # no locators
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()]),
    ])])
    apply_sequencing_debt_from_patch(mem, before_rs=before, after_rs=after, iteration=25)
    assert key in mem.continuity.posthoc_recheck_needed_debt


def test_apply_sequencing_debt_clears_posthoc_on_re_evaluation() -> None:
    """Third call with vb updated → posthoc AND earned debt both cleared."""
    mem = LoopMemoryState()
    key = _unit_key("item1", "u1")
    mem.continuity.earned_before_local_evidence_debt = {key: 23}
    mem.continuity.posthoc_recheck_needed_debt = {key: 25}

    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()]),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()], verification_basis="Confirmed"),
    ])])
    apply_sequencing_debt_from_patch(mem, before_rs=before, after_rs=after, iteration=30)
    assert key not in mem.continuity.posthoc_recheck_needed_debt
    # Re-evaluation also removes from earned debt — debt is "unresolved", not permanent history.
    assert key not in mem.continuity.earned_before_local_evidence_debt


def test_apply_sequencing_earned_debt_not_cleared_until_re_evaluation() -> None:
    """Earned debt stays while unit has only had locators added (posthoc, not re-evaluated)."""
    mem = LoopMemoryState()
    key = _unit_key("item1", "u1")
    mem.continuity.earned_before_local_evidence_debt = {key: 23}

    # Step: add locators post-hoc (no vb/dv change) → posthoc added, earned stays
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()]),
    ])])
    apply_sequencing_debt_from_patch(mem, before_rs=before, after_rs=after, iteration=25)
    assert key in mem.continuity.earned_before_local_evidence_debt, "Earned debt must remain until re-evaluation"
    assert key in mem.continuity.posthoc_recheck_needed_debt


def test_apply_sequencing_unrelated_earned_debt_not_cleared() -> None:
    """Re-evaluation of one unit does not clear earned debt for a different unit."""
    mem = LoopMemoryState()
    key_u1 = _unit_key("item1", "u1")
    key_u2 = _unit_key("item1", "u2")
    mem.continuity.earned_before_local_evidence_debt = {key_u1: 23, key_u2: 24}
    mem.continuity.posthoc_recheck_needed_debt = {key_u1: 25}

    # Re-evaluate u1 only
    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()]),
        _unit("u2", status="closed", determined_value="old"),
    ])])
    after = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", locators=[_locator()], verification_basis="Confirmed"),
        _unit("u2", status="closed", determined_value="old"),
    ])])
    apply_sequencing_debt_from_patch(mem, before_rs=before, after_rs=after, iteration=30)
    assert key_u1 not in mem.continuity.earned_before_local_evidence_debt
    assert key_u2 in mem.continuity.earned_before_local_evidence_debt, "u2 debt must be unaffected"


def test_apply_sequencing_same_turn_locator_and_re_eval_clears_earned_debt() -> None:
    """Same-turn locator + vb update clears earned debt even when posthoc stage was skipped."""
    mem = LoopMemoryState()
    key = _unit_key("item1", "u1")
    mem.continuity.earned_before_local_evidence_debt = {key: 23}
    # unit was never in posthoc debt (locators not previously added)
    mem.continuity.posthoc_recheck_needed_debt = {}

    before = _rs([_item("item1", units=[
        _unit("u1", status="closed", determined_value="42", verification_basis=None),
    ])])
    after = _rs([_item("item1", units=[
        _unit(
            "u1",
            status="closed",
            determined_value="42",
            verification_basis="Verified via inspection",
            locators=[_locator()],
        ),
    ])])
    apply_sequencing_debt_from_patch(mem, before_rs=before, after_rs=after, iteration=24)
    assert key not in mem.continuity.earned_before_local_evidence_debt, (
        "Same-turn locator + re-eval must clear earned debt without posthoc stage"
    )
    assert key not in mem.continuity.posthoc_recheck_needed_debt
