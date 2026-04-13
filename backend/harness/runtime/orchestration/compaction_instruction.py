"""Instruction text for continuity compaction mode."""

from __future__ import annotations

COMPACTION_INSTRUCTION: str = (
    "You are compacting carried continuity for the Plattera harness. "
    "The JSON packet below contains only the continuity rows that should be folded.\n"
    'Return exactly one JSON object matching this schema:\n{"compacted_continuity_summary": string}\n'
    "Fold journal_entries_to_fold, kernel_step_records_to_fold, and kernel_step_result_records_to_fold into a single "
    "replacement string for compacted_continuity_summary. If prior_compacted_continuity_summary is non-empty, merge coherently. "
    "target_compacted_summary_chars is a mechanical budget: aim for that many characters in compacted_continuity_summary "
    "(roughly plus or minus 25 percent is acceptable). Stay within the supplied facts. No markdown."
)
