"""Transcript-edit **default** checklist seed (bootstrap scaffolding only).

**Allowed uses**
- Initialize native transcript-edit rows when calling ``initialize_decision_ledger`` (persistence/mutation store).
- Provide **domain** slot tie-break ordering via ``TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY`` (re-exported from
  ``decision_ledger_adapter`` as ``TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY``).

**Not allowed (for runtime organized-work reads)**
- Treating these keys as the harness ontology or as the canonical closure/read model.
- Bypassing the unified envelope + closure read ledger when making operational closure/blocking decisions.

Organized-work **reads** must go through ``decision_ledger_adapter`` (unified + closure read), not this module.

The generic harness decision ledger does not define deed/PLSS slots. This list is **default scaffolding** so runs
can start before discovery-driven population exists; it is not a claim that every mission must use these keys.
"""
from __future__ import annotations

# (key, label, mapping_blocking_default)
DEFAULT_DECISION_SLOT_SPECS: list[tuple[str, str, bool]] = [
    ("township", "Township", True),
    ("range", "Range", True),
    ("section", "Section", True),
    ("tie_distance", "Tie Distance", True),
    ("tie_bearing", "Tie Bearing", True),
    ("acreage", "Acreage", False),
    ("closure_or_pob", "Closure / POB", True),
]

# Tie-break ordering for transcript-edit focus/state updates (domain hint only).
TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY: dict[str, int] = {
    "range": 0,
    "township": 1,
    "section": 2,
    "tie_distance": 3,
    "tie_bearing": 4,
    "closure_or_pob": 5,
    "acreage": 6,
}

DEFAULT_DECISION_SLOT_KEYS = frozenset(spec[0] for spec in DEFAULT_DECISION_SLOT_SPECS)
