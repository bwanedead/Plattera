"""Final package preview validation, repair packets, and minimum-shape guards."""

from __future__ import annotations

from typing import Any

from domains.mapping.deed_to_ir.payloads.published_output import ALLOWED_CLOSURE_DIMENSION_IDS

from .output_package_validation import (
    PUBLISH_PAYLOAD_VALIDATION_FAILED,
    PublishPayloadValidationError,
    validate_agent_output_rows,
)

FINAL_PACKAGE_INCOMPLETE = "final_package_incomplete"
MAX_ROW_KEY_SAMPLES = 4
MAX_KEYS_PER_SAMPLE = 12

ROW_CONTRACT_SUMMARY: dict[str, dict[str, Any]] = {
    "scope_results": {
        "required": ["scope_id", "status"],
        "optional": ["title", "summary", "basis_refs", "blocker_refs", "dependency_refs"],
    },
    "external_dependencies": {
        "required": ["dependency_id", "affected_scope", "description", "status"],
        "optional": ["available_refs"],
        "forbidden_common": ["title", "summary"],
    },
    "closure_dimensions": {
        "required": ["dimension_id", "status"],
        "optional": ["title", "summary", "basis_refs"],
    },
    "notes": {
        "required": ["note_id", "summary"],
        "optional": ["basis_refs"],
    },
    "upstream_corrections": {
        "required": [
            "correction_id",
            "posture",
            "resolution_used_by_ir",
            "recommended_action",
            "basis_refs",
            "rationale",
        ],
        "optional": [
            "title",
            "target_entity_id",
            "target_entity_type",
            "upstream_value",
            "corrected_value",
        ],
    },
}

PREPARE_VALIDATION_REPAIR_HINT = (
    "Repair the invalid fields while preserving valid sections from the previous attempt; "
    "do not drop scope_results, closure_dimensions, or notes unless intentionally changing "
    "the final package."
)

INCOMPLETE_REPAIR_HINT = (
    "A final package preview must carry scope results and all closure dimensions. "
    "Preserve already valid rows while repairing invalid fields."
)

_SECTION_FIELDS = (
    "scope_results",
    "external_dependencies",
    "closure_dimensions",
    "notes",
    "upstream_corrections",
)


class FinalPackageIncompleteError(Exception):
    """Retryable final package minimum-shape failure."""

    def __init__(
        self,
        *,
        missing_sections: list[str],
        missing_closure_dimensions: list[str],
    ) -> None:
        self.missing_sections = tuple(missing_sections)
        self.missing_closure_dimensions = tuple(missing_closure_dimensions)
        super().__init__(FINAL_PACKAGE_INCOMPLETE)


def validate_prepare_final_package_rows(
    *,
    scope_results: Any = None,
    external_dependencies: Any = None,
    closure_dimensions: Any = None,
    notes: Any = None,
    upstream_corrections: Any = None,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    """Validate agent rows for prepare; enforce minimum final-package shape."""
    try:
        scopes, deps, closure, note_rows, corrections = validate_agent_output_rows(
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        )
    except PublishPayloadValidationError as exc:
        raise _attach_prepare_repair_context(
            exc,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        ) from exc

    validate_final_package_minimum_shape(
        scope_results=scopes,
        closure_dimensions=closure,
    )
    return scopes, deps, closure, note_rows, corrections


def validate_final_package_minimum_shape(
    *,
    scope_results: list[dict[str, Any]],
    closure_dimensions: list[dict[str, Any]],
) -> None:
    missing_sections: list[str] = []
    if not scope_results:
        missing_sections.append("scope_results")
    if not closure_dimensions:
        missing_sections.append("closure_dimensions")

    present_dimension_ids = {
        str(row.get("dimension_id") or "").strip()
        for row in closure_dimensions
        if isinstance(row, dict) and str(row.get("dimension_id") or "").strip()
    }
    missing_closure_dimensions = sorted(
        dimension_id
        for dimension_id in ALLOWED_CLOSURE_DIMENSION_IDS
        if dimension_id not in present_dimension_ids
    )

    if missing_sections or missing_closure_dimensions:
        raise FinalPackageIncompleteError(
            missing_sections=missing_sections,
            missing_closure_dimensions=missing_closure_dimensions,
        )


def build_rejected_payload_summary(
    *,
    scope_results: Any,
    external_dependencies: Any,
    closure_dimensions: Any,
    notes: Any,
    upstream_corrections: Any = None,
) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for field_name, rows in (
        ("scope_results", scope_results),
        ("external_dependencies", external_dependencies),
        ("closure_dimensions", closure_dimensions),
        ("notes", notes),
        ("upstream_corrections", upstream_corrections),
    ):
        summary[field_name] = _summarize_section_rows(rows)
    return summary


def compute_preserve_sections(
    validation_errors: list[dict[str, str]],
    *,
    scope_results: Any,
    external_dependencies: Any,
    closure_dimensions: Any,
    notes: Any,
    upstream_corrections: Any = None,
) -> list[str]:
    sections_with_errors = _sections_with_validation_errors(validation_errors)
    preserve: list[str] = []
    for section, value in (
        ("scope_results", scope_results),
        ("external_dependencies", external_dependencies),
        ("closure_dimensions", closure_dimensions),
        ("notes", notes),
        ("upstream_corrections", upstream_corrections),
    ):
        if isinstance(value, list) and section not in sections_with_errors:
            preserve.append(section)
    return preserve


def build_prepare_validation_repair_packet(
    *,
    validation_errors: list[dict[str, str]],
    scope_results: Any,
    external_dependencies: Any,
    closure_dimensions: Any,
    notes: Any,
    upstream_corrections: Any = None,
) -> dict[str, Any]:
    return {
        "validation_errors": validation_errors,
        "rejected_payload_summary": build_rejected_payload_summary(
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        ),
        "row_contract_summary": dict(ROW_CONTRACT_SUMMARY),
        "repair_hint": PREPARE_VALIDATION_REPAIR_HINT,
        "preserve_sections": compute_preserve_sections(
            validation_errors,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        ),
    }


def final_package_prepare_validation_refusal(
    exc: PublishPayloadValidationError,
    *,
    scope_results: Any = None,
    external_dependencies: Any = None,
    closure_dimensions: Any = None,
    notes: Any = None,
    upstream_corrections: Any = None,
) -> dict[str, Any]:
    validation_errors = list(exc.validation_errors)
    repair_packet = exc.prepare_repair_packet
    if repair_packet is None:
        repair_packet = build_prepare_validation_repair_packet(
            validation_errors=validation_errors,
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        )
    reason_code = exc.reason_code or PUBLISH_PAYLOAD_VALIDATION_FAILED
    return {
        "executed": False,
        "reason_codes": [reason_code],
        "refusal": {
            "reason_code": reason_code,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": PUBLISH_PAYLOAD_VALIDATION_FAILED,
                "message": "publish payload validation failed",
            },
            **repair_packet,
        },
    }


def final_package_prepare_combined_refusal(
    *,
    validation_exc: PublishPayloadValidationError | None = None,
    expected_ir_artifact_ref: str | None = None,
    actual_ir_artifact_ref: str | None = None,
    scope_results: Any = None,
    external_dependencies: Any = None,
    closure_dimensions: Any = None,
    notes: Any = None,
    upstream_corrections: Any = None,
) -> dict[str, Any]:
    """Retryable refusal when row validation and mapping lineage both fail."""
    reason_codes: list[str] = []
    outputs: dict[str, Any] = {}
    if validation_exc is not None:
        reason_codes.append(validation_exc.reason_code or PUBLISH_PAYLOAD_VALIDATION_FAILED)
        repair_packet = validation_exc.prepare_repair_packet
        if repair_packet is None:
            repair_packet = build_prepare_validation_repair_packet(
                validation_errors=list(validation_exc.validation_errors),
                scope_results=scope_results,
                external_dependencies=external_dependencies,
                closure_dimensions=closure_dimensions,
                notes=notes,
                upstream_corrections=upstream_corrections,
            )
        outputs.update(repair_packet)
        outputs["error"] = {
            "code": validation_exc.reason_code or PUBLISH_PAYLOAD_VALIDATION_FAILED,
            "message": "publish payload validation failed",
        }
    if expected_ir_artifact_ref and actual_ir_artifact_ref and expected_ir_artifact_ref != actual_ir_artifact_ref:
        reason_codes.append("mapping_ir_lineage_mismatch")
        outputs["lineage_mismatch"] = {
            "expected_ir_artifact_ref": expected_ir_artifact_ref,
            "actual_ir_artifact_ref": actual_ir_artifact_ref,
            "repair_hint": (
                "Submit the expected IR for mapping, then publish the returned mapping artifact."
            ),
        }
        if "error" not in outputs:
            outputs["error"] = {
                "code": "mapping_ir_lineage_mismatch",
                "message": "mapping artifact was not produced from expected IR",
            }
    primary = reason_codes[0] if reason_codes else PUBLISH_PAYLOAD_VALIDATION_FAILED
    return {
        "executed": False,
        "reason_codes": reason_codes,
        "refusal": {
            "reason_code": primary,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": outputs,
    }


def final_package_incomplete_refusal(exc: FinalPackageIncompleteError) -> dict[str, Any]:
    return {
        "executed": False,
        "reason_codes": [FINAL_PACKAGE_INCOMPLETE],
        "refusal": {
            "reason_code": FINAL_PACKAGE_INCOMPLETE,
            "retryable": True,
            "blocked_by_invariant": False,
            "blocked_by_budget": False,
            "missing_inputs": [],
        },
        "outputs": {
            "error": {
                "code": FINAL_PACKAGE_INCOMPLETE,
                "message": "final package preview is missing required sections",
            },
            "missing_sections": list(exc.missing_sections),
            "missing_closure_dimensions": list(exc.missing_closure_dimensions),
            "repair_hint": INCOMPLETE_REPAIR_HINT,
        },
    }


def _attach_prepare_repair_context(
    exc: PublishPayloadValidationError,
    *,
    scope_results: Any,
    external_dependencies: Any,
    closure_dimensions: Any,
    notes: Any,
    upstream_corrections: Any = None,
) -> PublishPayloadValidationError:
    return PublishPayloadValidationError(
        exc.validation_errors,
        reason_code=exc.reason_code,
        prepare_repair_packet=build_prepare_validation_repair_packet(
            validation_errors=list(exc.validation_errors),
            scope_results=scope_results,
            external_dependencies=external_dependencies,
            closure_dimensions=closure_dimensions,
            notes=notes,
            upstream_corrections=upstream_corrections,
        ),
    )


def _sections_with_validation_errors(validation_errors: list[dict[str, str]]) -> set[str]:
    sections: set[str] = set()
    for err in validation_errors:
        path = str(err.get("path") or "")
        for section in _SECTION_FIELDS:
            if path == section or path.startswith(f"{section}["):
                sections.add(section)
                break
    return sections


def _summarize_section_rows(rows: Any) -> dict[str, Any]:
    if isinstance(rows, list):
        key_samples: list[list[str]] = []
        for row in rows[:MAX_ROW_KEY_SAMPLES]:
            if isinstance(row, dict):
                keys = sorted(str(key) for key in row.keys())[:MAX_KEYS_PER_SAMPLE]
                key_samples.append(keys)
        return {"count": len(rows), "row_keys": key_samples}

    section_summary: dict[str, Any] = {"count": 0, "row_keys": []}
    received_type = _received_type_label(rows)
    if received_type is not None:
        section_summary["received_type"] = received_type
    return section_summary


def _received_type_label(value: Any) -> str | None:
    if isinstance(value, list):
        return None
    if value is None:
        return "null"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__.lower()
