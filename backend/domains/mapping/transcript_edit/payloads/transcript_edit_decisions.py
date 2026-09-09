"""Domain-owned constants for revision-bound transcript edit provenance.

Tooling owns validation and persistence; this module owns the field name,
schema version, allowed lanes, determination vocabulary, and uncertainty
reason vocabulary.
"""

from __future__ import annotations

TRANSCRIPT_EDIT_DECISIONS_FIELD = "transcript_edit_decisions"
TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION = 2

TRANSCRIPT_EDIT_LANES: tuple[str, ...] = (
    "source_transcript_verbatim",
    "normalized_or_mapping_transcript",
)

DETERMINATION_PROVISIONAL = "provisional"
DETERMINATION_EARNED = "earned"
ALLOWED_DETERMINATIONS: frozenset[str] = frozenset(
    {DETERMINATION_PROVISIONAL, DETERMINATION_EARNED}
)

UNCERTAINTY_REASON_OBSERVER_DISAGREEMENT = "observer_disagreement"
UNCERTAINTY_REASON_SOURCE_AMBIGUOUS = "source_ambiguous"
UNCERTAINTY_REASON_PACKET_INSUFFICIENT = "packet_insufficient"
UNCERTAINTY_REASON_CONTEXT_INSUFFICIENT = "context_insufficient"
UNCERTAINTY_REASON_EVIDENCE_INCOMPLETE = "evidence_incomplete"
UNCERTAINTY_REASON_OTHER = "other"
ALLOWED_UNCERTAINTY_REASONS: frozenset[str] = frozenset(
    {
        UNCERTAINTY_REASON_OBSERVER_DISAGREEMENT,
        UNCERTAINTY_REASON_SOURCE_AMBIGUOUS,
        UNCERTAINTY_REASON_PACKET_INSUFFICIENT,
        UNCERTAINTY_REASON_CONTEXT_INSUFFICIENT,
        UNCERTAINTY_REASON_EVIDENCE_INCOMPLETE,
        UNCERTAINTY_REASON_OTHER,
    }
)

# Transport safety bounds (not semantic batching doctrine). Owned here so
# tool specs and tooling validators share one ceiling.
MAX_DECISIONS_PER_REQUEST = 32
MAX_PERSISTED_TRANSCRIPT_EDIT_DECISIONS = 256
MAX_UNCERTAINTY_REASONS_PER_DECISION = 4
MAX_EDITS_PER_DECISION = 16
MAX_EVIDENCE_REFS_PER_DECISION = 32
MAX_CANDIDATE_VALUES_PER_DECISION = 16
MAX_DECISION_ID_CHARS = 128
MAX_VERIFICATION_BASIS_CHARS = 4_000
MAX_EDIT_TEXT_CHARS = 100_000
MAX_CONTEXT_TEXT_CHARS = 8_000
MAX_REQUEST_SERIALIZED_CHARS = 500_000

# Compact handoff projection bounds (mechanical truncation only).
MAX_DECISION_SUMMARY_ROWS = 24
MAX_DECISION_SUMMARY_REPLACEMENT_CHARS = 160
MAX_DECISION_SUMMARY_BASIS_CHARS = 320
MAX_DECISION_SUMMARY_CANDIDATES = 8
MAX_DECISION_SUMMARY_EVIDENCE_REFS = 8
MAX_DECISION_SUMMARY_REPLACEMENTS = 8
# Hard ceiling on canonical compact JSON for prompt/handoff safety.
MAX_DECISION_SUMMARY_SERIALIZED_CHARS = 8_000
