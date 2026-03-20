"""Transcript-edit **default** checklist seed (bootstrap scaffolding only).

**Allowed uses**
- Initialize native transcript-edit rows when calling ``initialize_decision_ledger`` (persistence/mutation store).
- Provide **domain** slot tie-break ordering via ``TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY`` (alias of
  ``transcript_edit_bootstrap_hints.TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS``; re-exported from
  ``decision_ledger_adapter`` as ``TRANSCRIPT_EDIT_DOMAIN_SLOT_PRIORITY``).

**Not allowed (for runtime organized-work reads)**
- Treating these keys as the harness ontology or as the canonical closure/read model.
- Bypassing the unified envelope + closure read ledger when making operational closure/blocking decisions.

Organized-work **reads** must go through ``decision_ledger_adapter`` (unified + closure read), not this module.

**Phase 16:** This module is an **optional domain template policy** (``transcript_edit_ledger_bootstrap_policy``):
discovery-first organized work remains the default; these rows exist for mutation compatibility and wake only when
audit/orient/evidence requires them — not harness ontology.

The generic harness decision ledger does not define deed/PLSS slots. This list is **default scaffolding** so runs
can start before discovery-driven population exists; it is not a claim that every mission must use these keys.

Slot **tie-break ordering** is defined in ``transcript_edit_bootstrap_hints`` (``TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS``),
re-exported here as ``TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY`` for backward compatibility.
"""
from __future__ import annotations

from .transcript_edit_bootstrap_hints import TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS

# Re-export: same object as bootstrap hints (single source for ordering).
TRANSCRIPT_EDIT_DEFAULT_SLOT_PRIORITY: dict[str, int] = TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS

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

DEFAULT_DECISION_SLOT_KEYS = frozenset(spec[0] for spec in DEFAULT_DECISION_SLOT_SPECS)

# Phase 15: **no** default slots are awake at init — all bootstrap rows are dormant until
# audit, image check, or orient calls ``wake_seed_scaffolding_row`` (on-demand materialization of attention).
# Rows remain in ``items[]`` for mutation compatibility; ``SEED_WAKE_AT_INIT_KEYS`` is kept empty for clarity.
SEED_WAKE_AT_INIT_KEYS: frozenset[str] = frozenset()
