"""Domain-owned constants for unverified working-transcript initialization provenance.

Tooling owns validation and persistence; this module owns field names, schema
version, copy posture vocabulary, and copied-lane identity.
"""

from __future__ import annotations

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    TRANSCRIPT_EDIT_LANES,
)

INITIALIZATION_PROVENANCE_FIELD = "initialization_provenance"
INITIALIZATION_PROVENANCE_SCHEMA_VERSION = 1

COPY_POSTURE_UNVERIFIED_CANDIDATE = "unverified_candidate_copy"

# Both transcript lanes receive the same exact T0 text at initialization.
INITIALIZED_TRANSCRIPT_LANES: tuple[str, ...] = TRANSCRIPT_EDIT_LANES
