"""Generic prepare-deed-to-IR-final-package example request (no practice-deed tokens)."""

from __future__ import annotations

from typing import Any

from .published_output import ALLOWED_CLOSURE_DIMENSION_IDS


def build_prepare_deed_to_ir_final_package_example_request() -> dict[str, Any]:
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
                "correction_id": "example_inherited_operand_distance_correction",
                "title": "Example inherited operand distance correction",
                "target_entity_id": "example_call2_distance",
                "target_entity_type": "resolution_unit",
                "upstream_value": "410 feet",
                "corrected_value": "438 feet",
                "posture": "confirmed_from_source",
                "resolution_used_by_ir": True,
                "recommended_action": "transcript_amendment",
                "basis_refs": [
                    "transcript_edit:resolution_state:example",
                    "image:derived:example_source_crop",
                    "feature_graph:ir:example_bundle_v1",
                ],
                "rationale": (
                    "Final IR and mapping rely on the corrected distance; inherited mapping_operands "
                    "carried the upstream value but source evidence supports the corrected value."
                ),
            }
        ],
    }
