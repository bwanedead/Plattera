"""Advisory sequencing-debt detection for earned-before-evidence ordering violations.

Detects when a covered unit transitions to earned/closed with a compact exact
``determined_value`` before claim-local evidence (``evidence_locators``) exists,
and when locators are later attached post-hoc without re-evaluating the claim.

All logic is mechanical/structural only.  No domain content is inspected.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..memory.loop_state import LoopMemoryState
    from ...mission_state.contracts import ResolutionState


def _str_val(obj: Any, key: str) -> str:
    """Get a normalised lowercase string attribute/key value, or empty string."""
    if isinstance(obj, Mapping):
        val = obj.get(key)
    else:
        val = getattr(obj, key, None)
    return str(val or "").strip().lower()


def _get(obj: Any, key: str) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key)
    return getattr(obj, key, None)


def _is_earned_exact(unit: Any) -> bool:
    """True when the unit is in an earned/closed state AND has a determined_value.

    Excludes broad/group rows without a compact determined value.
    """
    status = _str_val(unit, "status")
    determination = _str_val(unit, "determination")
    determined_value = _get(unit, "determined_value")
    has_value = isinstance(determined_value, str) and bool(determined_value.strip())
    is_earned_or_closed = status == "closed" or determination == "earned"
    return is_earned_or_closed and has_value


def _has_locators(unit: Any) -> bool:
    """True when the unit has at least one evidence_locator."""
    locators = _get(unit, "evidence_locators")
    if isinstance(locators, (list, tuple)):
        return bool(locators)
    return False


def _unit_key(item_id: str, unit_id: str) -> str:
    return f"{item_id}//{unit_id}"


def _units_by_id(item: Any) -> dict[str, Any]:
    """Index covered_units by unit_id as dicts."""
    units = _get(item, "covered_units") or []
    out: dict[str, Any] = {}
    for unit in units:
        uid = _str_val(unit, "unit_id")
        if uid:
            out[uid] = unit
    return out


def _items_by_id(rs: Any) -> dict[str, Any]:
    items = getattr(rs, "items", None) or []
    out: dict[str, Any] = {}
    for item in items:
        iid = _str_val(item, "item_id")
        if iid:
            out[iid] = item
    return out


def _vb(unit: Any) -> str:
    return str(_get(unit, "verification_basis") or "").strip()


def _dv(unit: Any) -> str:
    return str(_get(unit, "determined_value") or "").strip()


def detect_sequencing_debts(
    before_rs: Any,
    after_rs: Any,
    *,
    existing_earned_debt: Mapping[str, int],
    existing_posthoc_debt: Mapping[str, int],
    iteration: int,
) -> tuple[dict[str, int], dict[str, int], set[str], set[str]]:
    """Compare before/after ResolutionState and return sequencing debt deltas.

    Returns
    -------
    new_earned_debt : dict[str, int]
        Unit keys that newly became earned-exact without claim-local locators.
        Value is the iteration when the debt was detected.
    new_posthoc_debt : dict[str, int]
        Unit keys (already in existing_earned_debt) that had locators added
        post-hoc in this patch without simultaneous re-evaluation.
        Value is the iteration.
    cleared_posthoc : set[str]
        Unit keys that were in existing_posthoc_debt and were re-evaluated in this
        patch (verification_basis changed, determined_value changed, or status
        reopened).  Strict subset of cleared_earned.
    cleared_earned : set[str]
        All unit keys whose earned sequencing debt is now resolved — includes
        cleared_posthoc plus keys that were in existing_earned_debt but NOT yet
        in posthoc debt and were re-evaluated or reopened in this same patch.
        Covers the "same-turn locators + re-eval" and "reopen before posthoc"
        cases that cleared_posthoc alone would miss.
    """
    before_items = _items_by_id(before_rs)
    after_items = _items_by_id(after_rs)

    new_earned_debt: dict[str, int] = {}
    new_posthoc_debt: dict[str, int] = {}
    cleared_posthoc: set[str] = set()
    cleared_earned: set[str] = set()

    for item_id, after_item in after_items.items():
        before_item = before_items.get(item_id)
        before_units = _units_by_id(before_item) if before_item is not None else {}
        after_units = _units_by_id(after_item)

        for unit_id, after_unit in after_units.items():
            key = _unit_key(item_id, unit_id)
            before_unit = before_units.get(unit_id)

            after_earned = _is_earned_exact(after_unit)
            before_earned = _is_earned_exact(before_unit) if before_unit is not None else False
            newly_earned = after_earned and not before_earned

            after_has_locators = _has_locators(after_unit)
            before_has_locators = _has_locators(before_unit) if before_unit is not None else False
            got_new_locators = after_has_locators and not before_has_locators

            # --- New earned-before-evidence debt ---
            # Unit became earned/exact in this patch AND still has no locators.
            if newly_earned and not after_has_locators and key not in existing_earned_debt:
                new_earned_debt[key] = iteration

            # --- Post-hoc locator added to an already-earned unit ---
            # The unit was previously in earned_before_local_evidence_debt, and
            # this patch added locators WITHOUT also re-evaluating the claim.
            if key in existing_earned_debt and got_new_locators:
                # Check if this same patch also re-evaluated the unit.
                vb_same = _vb(after_unit) == _vb(before_unit) if before_unit is not None else True
                dv_same = _dv(after_unit) == _dv(before_unit) if before_unit is not None else True
                still_earned = after_earned
                if vb_same and dv_same and still_earned:
                    # Post-hoc: locators added without re-evaluation.
                    if key not in existing_posthoc_debt and key not in cleared_posthoc:
                        new_posthoc_debt[key] = iteration

            # Shared helper: detect a material re-evaluation or reopen in this patch.
            _vb_changed = before_unit is not None and _vb(after_unit) != _vb(before_unit)
            _dv_changed = before_unit is not None and _dv(after_unit) != _dv(before_unit)
            _reopened = not after_earned
            _re_evaluated = _vb_changed or _dv_changed or _reopened

            # --- Clear post-hoc recheck debt when re-evaluated ---
            if key in existing_posthoc_debt and _re_evaluated:
                cleared_posthoc.add(key)
                cleared_earned.add(key)
                # Do not add to new_posthoc_debt if it was cleared in the same turn.
                new_posthoc_debt.pop(key, None)

            # --- Clear earned-only debt when directly re-evaluated or reopened ---
            # Handles "same-turn locators + re-eval" and "reopen before posthoc" shapes.
            if (
                key in existing_earned_debt
                and key not in existing_posthoc_debt
                and _re_evaluated
            ):
                cleared_earned.add(key)

    return new_earned_debt, new_posthoc_debt, cleared_posthoc, cleared_earned


def apply_sequencing_debt_from_patch(
    loop_memory: "LoopMemoryState",
    *,
    before_rs: Any,
    after_rs: Any,
    iteration: int,
) -> None:
    """Detect and persist sequencing debt deltas after a successful state-patch apply.

    Called immediately after ``loop_memory.continuity.resolution_state`` is updated
    to the new state.  Mutates the two debt dicts on ``loop_memory.continuity``.

    Debt lifecycle:
    - A unit enters ``earned_before_local_evidence_debt`` when it first commits to a
      value without claim-local locators.
    - When the agent later adds locators without re-evaluating the claim, the unit
      also enters ``posthoc_recheck_needed_debt``.
    - When the agent re-evaluates (changes ``verification_basis``, ``determined_value``,
      or reopens the unit), the key is removed from **both** debt dicts.  This keeps
      ``earned_before_local_evidence_debt`` as an "unresolved" tracker — every entry
      still needs a locator or a re-evaluation — not a permanent historical log.
    """
    cont = loop_memory.continuity
    new_earned, new_posthoc, cleared_posthoc, cleared_earned = detect_sequencing_debts(
        before_rs=before_rs,
        after_rs=after_rs,
        existing_earned_debt=dict(cont.earned_before_local_evidence_debt),
        existing_posthoc_debt=dict(cont.posthoc_recheck_needed_debt),
        iteration=iteration,
    )
    # Apply earned debt (additive until re-evaluation clears it).
    earned = dict(cont.earned_before_local_evidence_debt)
    earned.update(new_earned)
    # cleared_earned covers all resolved keys: posthoc-cleared + directly re-evaluated.
    for key in cleared_earned:
        earned.pop(key, None)
    cont.earned_before_local_evidence_debt = earned

    # Apply post-hoc debt, clearing re-evaluated entries first (posthoc-only subset).
    posthoc = dict(cont.posthoc_recheck_needed_debt)
    for key in cleared_posthoc:
        posthoc.pop(key, None)
    posthoc.update(new_posthoc)
    cont.posthoc_recheck_needed_debt = posthoc
