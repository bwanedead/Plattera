"""Bootstrap tie-break hints for transcript-edit (not ontology, not discovery output).

**Seam:** ``initialize_decision_ledger`` (in ``decision_ledger_state``) creates initial native
rows from ``transcript_edit_default_checklist_seed`` — that is **bootstrap scaffolding only**.

This module holds **ordering hints** shared by focus tie-breaks and adapter re-exports. It does
**not** import the default checklist seed (avoids coupling "hint ordering" to "which rows exist").

**Discovery-first:** additional native rows are merged separately (see ``transcript_edit_ledger_discovery_prep``);
they use row ``scope_priority`` in focus tie-breaks, not this seed hint map. This dict is not the universe of legitimate work.
"""
from __future__ import annotations

# Lower numbers = higher priority when breaking ties among unresolved items (bootstrap hint only).
TRANSCRIPT_EDIT_SLOT_PRIORITY_HINTS: dict[str, int] = {
    "range": 0,
    "township": 1,
    "section": 2,
    "tie_distance": 3,
    "tie_bearing": 4,
    "closure_or_pob": 5,
    "acreage": 6,
}
