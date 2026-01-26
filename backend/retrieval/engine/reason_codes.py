"""
Stable reason codes for doc-slice diagnostics.

These codes ensure deterministic, parseable failure states for UI/agents.
"""

from enum import Enum


class DiagnosticReasonCode(str, Enum):
    """
    Stable reason codes for slice diagnostic failures.

    Each code represents a specific failure mode that can be presented to
    users or agents for decision-making.
    """
    # Missing state
    MISSING_INDEX_STATE = "missing_index_state"

    # Stale states
    STALE_SIGNATURE_MISMATCH = "stale_signature_mismatch"
    STALE_IDENTITY_MISMATCH = "stale_identity_mismatch"

    # Orphaned states
    ORPHANED_NOT_IN_INVENTORY = "orphaned_not_in_inventory"

    # Unavailable states
    UNAVAILABLE_MISSING_CONTENT_HASH = "unavailable_missing_content_hash"
    UNAVAILABLE_HYDRATION_FAILED = "unavailable_hydration_failed"
    UNAVAILABLE_EMBEDDINGS_MISSING = "unavailable_embeddings_missing"
    UNAVAILABLE_RUNTIME_IDENTITY_MISSING = "unavailable_runtime_identity_missing"
    UNAVAILABLE_SCHEMA_VERSION_MISMATCH = "unavailable_schema_version_mismatch"
    UNAVAILABLE_NEEDS_FORCE_REPAIR = "unavailable_needs_force_repair"
    UNAVAILABLE_UNKNOWN = "unavailable_unknown"
