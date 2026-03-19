"""Transcript-edit hints for when harness work-board items are useful (not harness ontology).

These strings are injected into resolver/planner prompts as domain guidance only.
"""
from __future__ import annotations

# Mission-specific examples; generic promotion rules live in harness.work_board.emergence.
TRANSCRIPT_EDIT_EMERGENT_ITEM_HINTS: list[str] = [
    "A newly discovered mapping-critical dependency that is not yet a ledger decision row.",
    "Image-verification ambiguity where preserving an explicit investigation branch improves continuity.",
    "Source truncation, scan artifact, or orientation gap that risks silent loss of contradiction context.",
    "A contradiction cluster or tie-break dependency that deserves its own durable row (not a sticky-note paraphrase).",
]

WORK_BOARD_EMERGENCE_DOCTRINE: str = (
    "Harness work board items represent durable organized work units—not transient observations. "
    "Use move propose_work_board_changes only when coherence, closure-seeking progress, or continuity "
    "materially improves. Prefer op=attach_note with target_item_id when nuance matters but a full item "
    "would add noise. Each add_item must include substantive reason, and at least one structural signal "
    "(mapping_blocking impact, high materiality, non-empty dependencies, or evidence_refs). "
    "context_notes on items are non-canonical: they must not contradict structural fields. "
    "Do not restate ledger-mapped decision rows as emergent items when the ledger already owns that key."
)
