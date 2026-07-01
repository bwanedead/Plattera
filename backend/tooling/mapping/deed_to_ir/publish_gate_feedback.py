"""Compact publish gate categories and repair hints for deed-to-IR publish refusals."""

from __future__ import annotations

from typing import Any, Mapping

from .final_package_preview_projection import render_upstream_corrections_timeline_lines

PUBLISH_GATE_PREVIEW_PACKAGE_INVALID = "preview_package_invalid"
PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH = "mapping_lineage_mismatch"
PUBLISH_GATE_WORKSPACE_STORAGE_FAILURE = "workspace_storage_failure"
PUBLISH_GATE_POSTURE_AUDIT = "publish_posture_audit_gate"

POSTURE_AUDIT_REPAIR_HINT = (
    "Publish preview was not rejected. Patch readiness/audit posture if warranted, "
    "then retry the same final_package_preview_ref."
)

CLOSURE_ENFORCEMENT_POSTURE_REPAIR_HINT = (
    "Preview remains valid. Patch mission/closure posture if warranted, then retry "
    "publish with the same final_package_preview_ref."
)

_PREVIEW_INVALID_CODES = frozenset(
    {
        "final_package_preview_invalid",
        "final_package_preview_not_ready",
        "final_package_preview_not_found",
        "publish_payload_validation_failed",
        "final_package_incomplete",
        "final_package_preview_row_mutation_forbidden",
        "publish_request_ambiguous",
        "publish_target_required",
    }
)

_LINEAGE_CODES = frozenset(
    {
        "mapping_ir_lineage_mismatch",
        "final_package_preview_stale",
    }
)

_STORAGE_CODES = frozenset(
    {
        "workspace_identity_required",
        "invalid_scope_path",
        "publication_in_progress",
        "output_revision_exists",
        "final_pointer_write_failed",
        "transcription_id_required",
        "mapping_artifact_ref_required",
        "mapping_artifact_not_found",
        "mapping_package_not_found",
        "mapping_sidecar_missing",
    }
)

_POSTURE_AUDIT_PREFIXES = (
    "work_universe_publish_",
    "work_universe_complete_",
    "closure_publish_",
    "closure_complete_",
    "missing_required_output_artifact:",
)


def classify_publish_gate_reason(reason_code: str) -> str:
    code = str(reason_code or "").strip()
    if not code:
        return PUBLISH_GATE_PREVIEW_PACKAGE_INVALID
    if code in _PREVIEW_INVALID_CODES:
        return PUBLISH_GATE_PREVIEW_PACKAGE_INVALID
    if code in _LINEAGE_CODES:
        return PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH
    if code in _STORAGE_CODES:
        return PUBLISH_GATE_WORKSPACE_STORAGE_FAILURE
    if any(code.startswith(prefix) for prefix in _POSTURE_AUDIT_PREFIXES):
        return PUBLISH_GATE_POSTURE_AUDIT
    if code.startswith("mapping_") or code.startswith("ir_artifact"):
        return PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH
    return PUBLISH_GATE_PREVIEW_PACKAGE_INVALID


def publish_gate_repair_hint(*, reason_code: str, publish_gate_category: str) -> str:
    if publish_gate_category == PUBLISH_GATE_POSTURE_AUDIT:
        return POSTURE_AUDIT_REPAIR_HINT
    if publish_gate_category == PUBLISH_GATE_MAPPING_LINEAGE_MISMATCH:
        if reason_code == "final_package_preview_stale":
            return "Prepare a new final package preview from the current mapping revision."
        return "Submit the expected IR for mapping, then prepare and publish from a fresh preview."
    if publish_gate_category == PUBLISH_GATE_WORKSPACE_STORAGE_FAILURE:
        return "Fix workspace scope or storage preconditions, then retry publish with the same preview ref."
    return "Repair the final package preview rows or refs, then retry prepare or publish as appropriate."


def build_publish_gate_feedback(*, reason_code: str, message: str | None = None) -> dict[str, Any]:
    category = classify_publish_gate_reason(reason_code)
    feedback: dict[str, Any] = {
        "publish_gate_category": category,
        "publish_gate_reason_code": str(reason_code or "").strip(),
        "repair_hint": publish_gate_repair_hint(
            reason_code=str(reason_code or "").strip(),
            publish_gate_category=category,
        ),
        "preview_still_valid": category == PUBLISH_GATE_POSTURE_AUDIT,
    }
    if message:
        feedback["publish_gate_message"] = str(message).strip()
    return feedback


def enrich_publish_refusal_result(result: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(result, dict) or result.get("executed"):
        return result
    refusal = result.get("refusal")
    reason_code = ""
    message = None
    if isinstance(refusal, Mapping):
        reason_code = str(refusal.get("reason_code") or "").strip()
    error = result.get("outputs")
    if isinstance(error, Mapping):
        err = error.get("error")
        if isinstance(err, Mapping):
            message = str(err.get("message") or "").strip() or None
            reason_code = reason_code or str(err.get("code") or "").strip()
    reason_codes = result.get("reason_codes")
    if not reason_code and isinstance(reason_codes, list) and reason_codes:
        reason_code = str(reason_codes[0] or "").strip()
    if not reason_code:
        return result
    gate = build_publish_gate_feedback(reason_code=reason_code, message=message)
    outputs = dict(result.get("outputs") or {}) if isinstance(result.get("outputs"), Mapping) else {}
    outputs.update(gate)
    merged = dict(result)
    merged["outputs"] = outputs
    return merged


def build_final_output_summary(*, publish_succeeded: bool) -> dict[str, Any]:
    return {
        "ready_for_completion_candidate": bool(publish_succeeded),
        "hydrate_output_ref_optional": bool(publish_succeeded),
    }


def render_publish_gate_timeline_lines(
    *,
    reason_code: str | None,
    outputs: Mapping[str, Any] | None = None,
    indent: str = "  ",
) -> list[str]:
    code = str(reason_code or "").strip()
    if not code and isinstance(outputs, Mapping):
        code = str(outputs.get("publish_gate_reason_code") or "").strip()
        refusal_error = outputs.get("error")
        if not code and isinstance(refusal_error, Mapping):
            code = str(refusal_error.get("code") or "").strip()
    if not code:
        return []

    if isinstance(outputs, Mapping) and outputs.get("publish_gate_category"):
        category = str(outputs.get("publish_gate_category") or "").strip()
        repair_hint = str(outputs.get("repair_hint") or "").strip()
        preview_valid = outputs.get("preview_still_valid")
    else:
        gate = build_publish_gate_feedback(reason_code=code)
        category = gate["publish_gate_category"]
        repair_hint = gate["repair_hint"]
        preview_valid = gate["preview_still_valid"]

    lines = [
        f"{indent}publish_gate:",
        f"{indent}  category: {category}",
        f"{indent}  reason_code: {code}",
    ]
    if preview_valid is True:
        lines.append(f"{indent}  preview_still_valid: true")
    if repair_hint:
        lines.append(f"{indent}  repair_hint:")
        lines.extend(_indented_prose(repair_hint, indent=f"{indent}    "))
    return lines


def render_publish_output_summary_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    if not outputs.get("output_revision_ref"):
        return []
    summary = outputs.get("final_output_summary")
    if not isinstance(summary, Mapping):
        summary = build_final_output_summary(publish_succeeded=True)

    lines = [f"{indent}publish_output_summary:"]
    lines.append(f"{indent}  output_ref: {outputs.get('output_ref') or 'deed_to_ir:output'}")
    lines.append(f"{indent}  output_revision_ref: {outputs.get('output_revision_ref')}")
    ir_ref = outputs.get("ir_artifact_ref")
    mapping_ref = outputs.get("mapping_artifact_ref")
    if ir_ref:
        lines.append(f"{indent}  ir_artifact_ref: {ir_ref}")
    if mapping_ref:
        lines.append(f"{indent}  mapping_artifact_ref: {mapping_ref}")
    scope_count = outputs.get("scope_result_count")
    if scope_count is not None:
        lines.append(f"{indent}  scope_result_count: {scope_count}")
    scope_statuses = outputs.get("scope_status_counts")
    if isinstance(scope_statuses, Mapping) and scope_statuses:
        parts = [f"{key}={value}" for key, value in sorted(scope_statuses.items())]
        lines.append(f"{indent}  scope_status_counts: {', '.join(parts)}")
    dep_count = outputs.get("external_dependency_count")
    if dep_count is not None:
        lines.append(f"{indent}  external_dependency_count: {dep_count}")
    closure_count = outputs.get("closure_dimension_count")
    if closure_count is not None:
        lines.append(f"{indent}  closure_dimension_count: {closure_count}")
    closure_statuses = outputs.get("closure_dimension_statuses")
    if isinstance(closure_statuses, list) and closure_statuses:
        parts = []
        for row in closure_statuses[:8]:
            if isinstance(row, Mapping):
                parts.append(
                    f"{row.get('dimension_id') or '?'}={row.get('status') or '?'}"
                )
        if parts:
            lines.append(f"{indent}  closure_dimension_statuses: {', '.join(parts)}")
    lines.extend(
        render_upstream_corrections_timeline_lines(
            upstream_correction_count=outputs.get("upstream_correction_count"),
            upstream_correction_summaries=outputs.get("upstream_correction_summaries")
            if isinstance(outputs.get("upstream_correction_summaries"), list)
            else None,
            indent=f"{indent}  ",
        )
    )
    if summary.get("ready_for_completion_candidate") is not None:
        lines.append(
            f"{indent}  ready_for_completion_candidate: "
            f"{str(bool(summary.get('ready_for_completion_candidate'))).lower()}"
        )
    if summary.get("hydrate_output_ref_optional") is not None:
        lines.append(
            f"{indent}  hydrate_output_ref_optional: "
            f"{str(bool(summary.get('hydrate_output_ref_optional'))).lower()}"
        )
    if summary.get("ready_for_completion_candidate") is True:
        lines.append(f"{indent}  expected_next: complete_run")
    return lines


def render_publish_tool_output(
    outputs: Mapping[str, Any] | None,
    *,
    reason_code: str | None = None,
    indent: str = "  ",
) -> list[str]:
    if isinstance(outputs, Mapping) and outputs.get("output_revision_ref"):
        return render_publish_output_summary_timeline_lines(outputs, indent=indent)
    return render_publish_gate_timeline_lines(
        reason_code=reason_code,
        outputs=outputs,
        indent=indent,
    )


def _indented_prose(text: str, *, indent: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text).splitlines():
        stripped = raw.strip()
        if stripped:
            lines.append(f"{indent}{stripped}")
    if not lines and text.strip():
        lines.append(f"{indent}{text.strip()}")
    return lines


def build_closure_enforcement_block_feedback(
    *,
    blocked_action_id: str,
    reason_code: str,
    message: str | None = None,
    preview_still_valid: bool | None = None,
    next_repair_action: str | None = None,
) -> dict[str, Any]:
    category = classify_publish_gate_reason(reason_code)
    feedback: dict[str, Any] = {
        "blocked_action_id": str(blocked_action_id or "").strip() or "unknown",
        "closure_enforcement_reason_code": str(reason_code or "").strip(),
        "publish_gate_category": category,
        "blocking_categories": [category],
    }
    if message:
        feedback["closure_enforcement_message"] = str(message).strip()
    if preview_still_valid is True:
        feedback["preview_still_valid"] = True
    elif preview_still_valid is False:
        feedback["preview_still_valid"] = False
    elif category == PUBLISH_GATE_POSTURE_AUDIT:
        feedback["preview_still_valid"] = True
    if next_repair_action:
        feedback["next_repair_action"] = next_repair_action
    elif category == PUBLISH_GATE_POSTURE_AUDIT:
        feedback["next_repair_action"] = CLOSURE_ENFORCEMENT_POSTURE_REPAIR_HINT
    else:
        feedback["next_repair_action"] = publish_gate_repair_hint(
            reason_code=str(reason_code or "").strip(),
            publish_gate_category=category,
        )
    return feedback


def render_closure_enforcement_blocked_timeline_lines(
    feedback: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(feedback, Mapping) or not feedback:
        return []
    lines = [f"{indent}closure_enforcement_blocked:"]
    blocked = feedback.get("blocked_action_id")
    if blocked:
        lines.append(f"{indent}  blocked_action_id: {blocked}")
    reason = feedback.get("closure_enforcement_reason_code")
    if reason:
        lines.append(f"{indent}  reason_code: {reason}")
    category = feedback.get("publish_gate_category")
    if category:
        lines.append(f"{indent}  blocking_category: {category}")
    categories = feedback.get("blocking_categories")
    if isinstance(categories, list) and categories:
        lines.append(f"{indent}  blocking_categories: {', '.join(str(c) for c in categories[:6])}")
    preview_valid = feedback.get("preview_still_valid")
    if preview_valid is True:
        lines.append(f"{indent}  preview_still_valid: true")
    elif preview_valid is False:
        lines.append(f"{indent}  preview_still_valid: false")
    repair = feedback.get("next_repair_action")
    if repair:
        lines.append(f"{indent}  next_repair_action:")
        lines.extend(_indented_prose(str(repair), indent=f"{indent}    "))
    message = feedback.get("closure_enforcement_message")
    if message:
        lines.append(f"{indent}  message:")
        lines.extend(_indented_prose(str(message), indent=f"{indent}    "))
    return lines
