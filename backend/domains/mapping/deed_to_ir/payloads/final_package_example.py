"""Generic prepare-deed-to-IR-final-package example request (no practice-deed tokens)."""

from __future__ import annotations

from typing import Any

from .published_output import ALLOWED_CLOSURE_DIMENSION_IDS


def build_prepare_deed_to_ir_final_package_example_request() -> dict[str, Any]:
    """Preferred intent-first example (fresh-run compact dispositions)."""
    return {
        "use_current_mapping_lineage": True,
        "correction_decisions": [
            {
                "target_entity_id": "example_call_2_distance",
                "posture": "confirmed_from_source",
                "resolution_used_by_ir": True,
                "recommended_action": "transcript_amendment",
                "rationale": (
                    "Targeted source evidence supports the corrected course distance "
                    "and the repaired mapping is the intended scoped handoff."
                ),
            }
        ],
        "dependency_decisions": [
            {
                "candidate_id": "example_scope_beta_continuation_source",
                "disposition": "include",
                "status": "missing",
            }
        ],
        "scope_dispositions": [
            {"scope_id": "example_scope_alpha", "status": "handoffable"},
            {"scope_id": "example_scope_beta", "status": "blocked"},
        ],
        "closure_dispositions": [
            {
                "dimension_id": dimension_id,
                "status": "partial" if dimension_id.endswith("scoped_completion") else "closed",
            }
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ],
    }


def build_prepare_deed_to_ir_final_package_explicit_example_request() -> dict[str, Any]:
    return {
        "mapping_artifact_ref": "feature_graph:mapping:mapping_example_bundle_ab12cd34",
        "expected_ir_artifact_ref": "feature_graph:ir:example_bundle_v1",
        "scope_results": [
            {
                "scope_id": "example_scope_alpha",
                "status": "handoffable",
                "title": "Primary scope",
                "summary": "Primary scope is represented in IR and the selected mapping revision.",
                "basis_refs": [
                    "feature_graph:ir:example_bundle_v1",
                    "feature_graph:mapping:mapping_example_bundle_ab12cd34",
                ],
                "blocker_refs": [],
                "dependency_refs": [],
            },
            {
                "scope_id": "example_scope_beta",
                "status": "blocked",
                "title": "Secondary scope",
                "summary": "Secondary scope remains blocked pending an external continuation source.",
                "basis_refs": [],
                "blocker_refs": ["missing_continuation_source"],
                "dependency_refs": ["missing_continuation_source"],
            },
        ],
        "external_dependencies": [
            {
                "dependency_id": "missing_continuation_source",
                "affected_scope": "example_scope_beta",
                "description": "External continuation source required to complete the blocked scope.",
                "status": "missing",
                "available_refs": [],
            }
        ],
        "closure_dimensions": [
            {
                "dimension_id": dimension_id,
                "status": "partial" if dimension_id.endswith("scoped_completion") else "closed",
                "summary": f"Example closure posture for {dimension_id}.",
                "basis_refs": ["feature_graph:mapping:mapping_example_bundle_ab12cd34"],
            }
            for dimension_id in sorted(ALLOWED_CLOSURE_DIMENSION_IDS)
        ],
        "notes": [
            {
                "note_id": "example_handoff_context_note",
                "summary": "Example non-blocking handoff context (not an upstream correction report).",
                "basis_refs": [],
            }
        ],
        "upstream_corrections": [
            {
                "correction_id": "example_call_2_distance_source_repair",
                "title": "Example call 2 distance source repair",
                "target_entity_id": "example_call_2_distance",
                "target_entity_type": "resolution_unit",
                "upstream_value": "430 feet",
                "corrected_value": "410 feet",
                "posture": "confirmed_from_source",
                "resolution_used_by_ir": True,
                "recommended_action": "transcript_amendment",
                "basis_refs": [
                    "image:derived:example_source_crop",
                    "feature_graph:ir:example_scope_v1",
                    "feature_graph:mapping:mapping_example_bundle_ab12cd34",
                ],
                "rationale": (
                    "Source evidence and mapping sanity supported the corrected course distance "
                    "used by the final IR."
                ),
            }
        ],
    }
