"""Domain-owned constants for revision-bound transcript edit provenance.

Tooling owns validation and persistence; this module owns the field name,
schema version, allowed lanes, and determination vocabulary.
"""

from __future__ import annotations

TRANSCRIPT_EDIT_DECISIONS_FIELD = "transcript_edit_decisions"
TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION = 1

TRANSCRIPT_EDIT_LANES: tuple[str, ...] = (
    "source_transcript_verbatim",
    "normalized_or_mapping_transcript",
)

DETERMINATION_PROVISIONAL = "provisional"
DETERMINATION_EARNED = "earned"
ALLOWED_DETERMINATIONS: frozenset[str] = frozenset(
    {DETERMINATION_PROVISIONAL, DETERMINATION_EARNED}
)

# Transport safety bounds (not semantic batching doctrine). Owned here so
# tool specs and tooling validators share one ceiling.
MAX_DECISIONS_PER_REQUEST = 32
MAX_EDITS_PER_DECISION = 16
MAX_EVIDENCE_REFS_PER_DECISION = 32
MAX_CANDIDATE_VALUES_PER_DECISION = 16
MAX_DECISION_ID_CHARS = 128
MAX_VERIFICATION_BASIS_CHARS = 4_000
MAX_EDIT_TEXT_CHARS = 100_000
MAX_CONTEXT_TEXT_CHARS = 8_000
MAX_REQUEST_SERIALIZED_CHARS = 500_000
