"""Neutral structural artifact-ref field vocabularies for transcript-edit tooling.

One module, consumer-specific sets: action-result remapping stays on its original
scalar/list lanes; storage audit uses those bases unioned with audit-only lanes
(including mapping-valued ``latest_refs``). Do not treat prose strings as refs.
"""

from __future__ import annotations

# ── Action-result remapping (original production vocabulary) ─────────────────

ACTION_RESULT_SINGLE_REF_KEYS = frozenset(
    {
        "ref_id",
        "derived_ref_id",
        "parent_ref_id",
        "root_source_ref",
        "source_ref",
        "working_draft_ref",
        "aggregate_working_ref",
        "base_revision_ref",
        "source_revision_ref",
        "previous_crop_set_overlay_ref",
        "view_of_crop_set_overlay_ref",
        "adjustment_source_ref",
        "crop_set_overlay_ref",
        "master_overlay_ref",
        "crop_ref",
        "local_source_ref",
        "placement_surface_ref",
        "source_unwrapped_from_ref",
        "rendered_ref",
    }
)

ACTION_RESULT_COLLECTION_REF_KEYS = frozenset(
    {
        "artifact_refs",
        "evidence_refs",
    }
)

# ── Audit-only extensions (read-only reference indexing) ─────────────────────

_AUDIT_ONLY_SINGLE_REF_KEYS = frozenset(
    {
        "primary_evidence_ref",
        "annotated_evidence_ref",
    }
)

_AUDIT_ONLY_COLLECTION_REF_KEYS = frozenset(
    {
        "context_refs",
    }
)

AUDIT_MAPPING_REF_KEYS = frozenset(
    {
        "latest_refs",
    }
)

AUDIT_SINGLE_REF_KEYS = ACTION_RESULT_SINGLE_REF_KEYS | _AUDIT_ONLY_SINGLE_REF_KEYS
AUDIT_COLLECTION_REF_KEYS = ACTION_RESULT_COLLECTION_REF_KEYS | _AUDIT_ONLY_COLLECTION_REF_KEYS
