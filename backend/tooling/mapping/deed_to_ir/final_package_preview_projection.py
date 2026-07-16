"""Timeline and hydration projection helpers for deed-to-IR final package preview."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .correction_lane_advisory import render_correction_lane_advisory_timeline_lines
from .correction_posture import render_upstream_corrections_required_timeline_lines
from .final_package_retry_projection import render_retry_package_shell_timeline_lines

PREPARE_PREVIEW_OUTPUT_TOP_LEVEL_KEYS: tuple[str, ...] = (
    "final_package_preview_ref",
    "final_package_preview_revision_ref",
    "working_preview_ref",
    "recommended_publish_request",
    "preview_ready_summary",
    "publish_ready_candidate",
)

# Present on intent-first prepare success; not required on the explicit path.
INTENT_FIRST_PREPARE_OUTPUT_KEYS: tuple[str, ...] = (
    "finalization_status",
    "selected_lineage",
    "correction_summary",
    "current_mapping_lineage",
)


def build_recommended_publish_request(*, preview_revision_ref: str) -> dict[str, str]:
    return {"final_package_preview_ref": preview_revision_ref}


def build_preview_ready_summary(*, publish_ready_candidate: bool) -> dict[str, Any] | None:
    if not publish_ready_candidate:
        return None
    return {
        "ready_for_publish_candidate": True,
        "expected_next": "publish_deed_to_ir_output",
        "hydrate_preview_optional": True,
        "state_alignment_optional": True,
    }


def enrich_prepare_preview_tool_outputs(
    outputs: dict[str, Any],
    *,
    preview_revision_ref: str,
    preview_ref: str,
) -> dict[str, Any]:
    """Attach stable preview ref aliases and mechanical next-step summary."""
    outputs["final_package_preview_ref"] = preview_ref
    outputs["final_package_preview_revision_ref"] = preview_revision_ref
    outputs["working_preview_ref"] = preview_revision_ref
    outputs["recommended_publish_request"] = build_recommended_publish_request(
        preview_revision_ref=preview_revision_ref,
    )
    ready_summary = build_preview_ready_summary(
        publish_ready_candidate=bool(outputs.get("publish_ready_candidate")),
    )
    if ready_summary is not None:
        outputs["preview_ready_summary"] = ready_summary
    return outputs


def compact_upstream_correction_summaries(
    rows: list[dict[str, Any]] | list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        correction_id = row.get("correction_id")
        if not correction_id:
            continue
        summaries.append(
            {
                "correction_id": correction_id,
                "posture": row.get("posture"),
                "recommended_action": row.get("recommended_action"),
                "target_entity_id": row.get("target_entity_id"),
                "resolution_used_by_ir": row.get("resolution_used_by_ir"),
            }
        )
    return summaries


def render_upstream_corrections_timeline_lines(
    *,
    upstream_correction_count: int | None = None,
    upstream_correction_summaries: list[Mapping[str, Any]] | None = None,
    upstream_corrections: list[Mapping[str, Any]] | None = None,
    indent: str = "  ",
) -> list[str]:
    summaries = upstream_correction_summaries
    if summaries is None and isinstance(upstream_corrections, list):
        summaries = compact_upstream_correction_summaries(list(upstream_corrections))
    if not isinstance(summaries, list):
        summaries = []
    count = upstream_correction_count
    if count is None:
        count = len(summaries)
    if not count:
        return []
    lines = [f"{indent}upstream_corrections: {count}"]
    for row in summaries:
        if not isinstance(row, Mapping):
            continue
        correction_id = str(row.get("correction_id") or "").strip()
        if not correction_id:
            continue
        parts = [f"posture={row.get('posture') or '?'}"]
        action = row.get("recommended_action")
        if action:
            parts.append(f"action={action}")
        target = row.get("target_entity_id")
        if target:
            parts.append(f"target={target}")
        used = row.get("resolution_used_by_ir")
        if used is not None:
            parts.append(f"used_by_ir={str(bool(used)).lower()}")
        lines.append(f"{indent}- {correction_id} {' '.join(parts)}")
    return lines


def compact_preview_row_summaries(
    *,
    scope_results: list[dict[str, Any]],
    external_dependencies: list[dict[str, Any]],
    closure_dimensions: list[dict[str, Any]],
    notes: list[dict[str, Any]],
    upstream_corrections: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scope_summaries = [
        {"scope_id": row.get("scope_id"), "status": row.get("status")}
        for row in scope_results
        if isinstance(row, dict) and row.get("scope_id")
    ]
    closure_dimension_statuses = [
        {"dimension_id": row.get("dimension_id"), "status": row.get("status")}
        for row in closure_dimensions
        if isinstance(row, dict) and row.get("dimension_id")
    ]
    corrections = upstream_corrections or []
    return {
        "scope_summaries": scope_summaries,
        "scope_result_count": len(scope_results),
        "external_dependency_count": len(external_dependencies),
        "closure_dimension_statuses": closure_dimension_statuses,
        "closure_dimension_count": len(closure_dimensions),
        "note_count": len(notes),
        "upstream_correction_count": len(corrections),
        "upstream_correction_summaries": compact_upstream_correction_summaries(corrections),
    }


def build_preview_hydration_payload(
    *,
    ref_id: str,
    preview: Mapping[str, Any],
    preview_revision_ref: str,
) -> dict[str, Any]:
    selected = preview.get("selected_artifacts")
    selected_dict = dict(selected) if isinstance(selected, Mapping) else {}
    row_summaries = compact_preview_row_summaries(
        scope_results=list(preview.get("scope_results") or [])
        if isinstance(preview.get("scope_results"), list)
        else [],
        external_dependencies=list(preview.get("external_dependencies") or [])
        if isinstance(preview.get("external_dependencies"), list)
        else [],
        closure_dimensions=list(preview.get("closure_dimensions") or [])
        if isinstance(preview.get("closure_dimensions"), list)
        else [],
        notes=list(preview.get("notes") or []) if isinstance(preview.get("notes"), list) else [],
        upstream_corrections=list(preview.get("upstream_corrections") or [])
        if isinstance(preview.get("upstream_corrections"), list)
        else [],
    )
    return {
        "ref_id": ref_id,
        "artifact_type": "deed_to_ir_final_package_preview",
        "schema_version": preview.get("schema_version"),
        "final_package_preview_ref": ref_id,
        "final_package_preview_revision_ref": preview_revision_ref,
        "selected_artifacts": selected_dict,
        **row_summaries,
        "review_summary": preview.get("mechanical_review_summary"),
        "lineage_summary": preview.get("lineage_summary"),
        "publish_ready_candidate": preview.get("publish_ready_candidate"),
        **(
            {"correction_lane_advisory": preview.get("correction_lane_advisory")}
            if isinstance(preview.get("correction_lane_advisory"), Mapping)
            else {}
        ),
    }


def render_final_package_preview_timeline_lines(
    preview: Mapping[str, Any] | None,
    *,
    preview_ref: str | None = None,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(preview, Mapping) or not preview:
        return []
    lines = [f"{indent}Final package preview:"]
    ref = preview_ref or preview.get("final_package_preview_revision_ref") or preview.get(
        "final_package_preview_ref"
    )
    if isinstance(ref, str) and ref.strip():
        lines.append(f"{indent}  preview_ref: {ref.strip()}")

    selected = preview.get("selected_artifacts")
    if isinstance(selected, Mapping):
        ir_ref = selected.get("ir_artifact_ref")
        mapping_ref = selected.get("mapping_artifact_ref")
        if isinstance(ir_ref, str) and ir_ref.strip():
            lines.append(f"{indent}  selected IR: {ir_ref.strip()}")
        if isinstance(mapping_ref, str) and mapping_ref.strip():
            lines.append(f"{indent}  mapping: {mapping_ref.strip()}")

    scope_summaries = preview.get("scope_summaries")
    if not isinstance(scope_summaries, list):
        scope_results = preview.get("scope_results")
        if isinstance(scope_results, list):
            scope_summaries = [
                {"scope_id": row.get("scope_id"), "status": row.get("status")}
                for row in scope_results
                if isinstance(row, Mapping) and row.get("scope_id")
            ]
    if isinstance(scope_summaries, list) and scope_summaries:
        parts = [
            f"{row.get('scope_id')}={row.get('status')}"
            for row in scope_summaries
            if isinstance(row, Mapping) and row.get("scope_id")
        ]
        if parts:
            lines.append(f"{indent}  scopes: {', '.join(parts)}")

    dep_count = preview.get("external_dependency_count")
    if dep_count is None:
        deps = preview.get("external_dependencies")
        if isinstance(deps, list):
            dep_count = len(deps)
    if isinstance(dep_count, int):
        lines.append(f"{indent}  dependencies: {dep_count}")

    lines.extend(
        render_upstream_corrections_timeline_lines(
            upstream_correction_count=preview.get("upstream_correction_count"),
            upstream_correction_summaries=preview.get("upstream_correction_summaries")
            if isinstance(preview.get("upstream_correction_summaries"), list)
            else None,
            upstream_corrections=preview.get("upstream_corrections")
            if isinstance(preview.get("upstream_corrections"), list)
            else None,
            indent=f"{indent}  ",
        )
    )
    lines.extend(
        render_correction_lane_advisory_timeline_lines(
            preview.get("correction_lane_advisory")
            if isinstance(preview.get("correction_lane_advisory"), Mapping)
            else None,
            indent=f"{indent}  ",
        )
    )

    closure_statuses = preview.get("closure_dimension_statuses")
    if not isinstance(closure_statuses, list):
        closure_dims = preview.get("closure_dimensions")
        if isinstance(closure_dims, list):
            closure_statuses = [
                {"dimension_id": row.get("dimension_id"), "status": row.get("status")}
                for row in closure_dims
                if isinstance(row, Mapping) and row.get("dimension_id")
            ]
    if isinstance(closure_statuses, list) and closure_statuses:
        parts = []
        for row in closure_statuses:
            if not isinstance(row, Mapping):
                continue
            dimension_id = str(row.get("dimension_id") or "")
            status = row.get("status")
            if not dimension_id:
                continue
            short_id = dimension_id.removeprefix("layer_").split("_", 1)[0]
            if short_id.isdigit():
                label = f"layer_{short_id}"
            else:
                label = dimension_id
            parts.append(f"{label}={status}")
        if parts:
            lines.append(f"{indent}  closure: {', '.join(parts)}")

    ready = preview.get("publish_ready_candidate")
    if ready is not None:
        lines.append(f"{indent}  publish_ready_candidate: {str(bool(ready)).lower()}")

    recommended = preview.get("recommended_publish_request")
    if isinstance(recommended, Mapping):
        preview_publish_ref = recommended.get("final_package_preview_ref")
        if isinstance(preview_publish_ref, str) and preview_publish_ref.strip():
            lines.append(
                f"{indent}  recommended_publish_request: "
                f"final_package_preview_ref={preview_publish_ref.strip()}"
            )

    ready_summary = preview.get("preview_ready_summary")
    if isinstance(ready_summary, Mapping) and ready_summary:
        lines.append(f"{indent}preview_ready_summary:")
        if ready_summary.get("ready_for_publish_candidate") is not None:
            lines.append(
                f"{indent}  ready_for_publish_candidate: "
                f"{str(bool(ready_summary.get('ready_for_publish_candidate'))).lower()}"
            )
        if ready_summary.get("expected_next"):
            lines.append(f"{indent}  expected_next: {ready_summary.get('expected_next')}")
        if ready_summary.get("hydrate_preview_optional") is True:
            lines.append(f"{indent}  hydrate_preview_optional: true")

    return lines


def render_final_package_validation_timeline_lines(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(outputs, Mapping):
        return []
    # Unified decision card is rendered once via prepare preview output.
    if outputs.get("finalization_decision_card"):
        return []
    from .intent_first_prepare import render_intent_first_prepare_timeline_lines

    intent_lines = render_intent_first_prepare_timeline_lines(outputs, indent=indent)
    refusal_lines = render_upstream_corrections_required_timeline_lines(outputs, indent=indent)
    if refusal_lines:
        return intent_lines + refusal_lines if intent_lines else refusal_lines
    # Intent-first missing-decision / lineage refusals (no classic validation_errors).
    if intent_lines and (
        outputs.get("missing_finalization_decisions")
        or outputs.get("current_mapping_lineage")
        or outputs.get("missing_correction_targets")
        or outputs.get("missing_dependency_decisions")
        or outputs.get("known_dependency_candidates")
        or outputs.get("dependency_candidate_diagnostics")
        or outputs.get("finalization_decision_card")
    ):
        return intent_lines
    validation_errors = outputs.get("validation_errors")
    rejected_summary = outputs.get("rejected_payload_summary")
    preserve_sections = outputs.get("preserve_sections")
    if not isinstance(validation_errors, list) and not isinstance(rejected_summary, Mapping):
        missing_sections = outputs.get("missing_sections")
        if isinstance(missing_sections, list) and missing_sections:
            lines = [f"{indent}final_package_validation:"]
            lines.append(f"{indent}  incomplete_sections: {', '.join(str(item) for item in missing_sections)}")
            missing_closure = outputs.get("missing_closure_dimensions")
            if isinstance(missing_closure, list) and missing_closure:
                lines.append(
                    f"{indent}  missing_closure_dimensions: {', '.join(str(item) for item in missing_closure)}"
                )
            return lines
        return intent_lines
    # Classic validation rendering — keep intent lines first when present.
    lines = list(intent_lines)
    lines.append(f"{indent}final_package_validation:")
    if isinstance(validation_errors, list) and validation_errors:
        lines.append(f"{indent}  errors:")
        for err in validation_errors[:12]:
            if not isinstance(err, Mapping):
                continue
            path = str(err.get("path") or "payload")
            code = str(err.get("code") or "invalid")
            message = str(err.get("message") or code)
            lines.append(f"{indent}    - {path} {code}: {message}")

    if isinstance(rejected_summary, Mapping):
        lines.append(f"{indent}  rejected_payload_summary:")
        for section, payload in rejected_summary.items():
            if not isinstance(payload, Mapping):
                continue
            count = payload.get("count", 0)
            received_type = payload.get("received_type")
            row_keys = payload.get("row_keys")
            if isinstance(row_keys, list) and row_keys:
                rendered_keys = []
                for sample in row_keys[:4]:
                    if isinstance(sample, list):
                        rendered_keys.append("[" + ",".join(str(key) for key in sample) + "]")
                keys_text = ", ".join(rendered_keys) if rendered_keys else "[]"
            else:
                keys_text = "[]"
            parts = [f"count={count}"]
            if received_type:
                parts.append(f"received_type={received_type}")
            parts.append(f"keys={keys_text}")
            lines.append(f"{indent}    {section}: {' '.join(parts)}")

    if isinstance(preserve_sections, list) and preserve_sections:
        lines.append(
            f"{indent}  preserve_sections: {', '.join(str(item) for item in preserve_sections)}"
        )

    return lines


def render_final_package_validation_tool_output(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    return render_final_package_validation_timeline_lines(outputs, indent=indent)


def render_final_package_preview_tool_output(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    """Render final package preview from prepare outputs or hydrate result rows."""
    if not isinstance(outputs, Mapping):
        return []
    from .intent_first_prepare import render_intent_first_prepare_timeline_lines
    from .mapping_lineage import render_current_mapping_lineage_timeline_lines

    lines: list[str] = []
    lines.extend(render_intent_first_prepare_timeline_lines(outputs, indent=indent))
    lines.extend(
        render_current_mapping_lineage_timeline_lines(
            outputs.get("current_mapping_lineage")
            if isinstance(outputs.get("current_mapping_lineage"), Mapping)
            else None,
            indent=indent,
        )
    )
    top_level = {
        key: outputs.get(key)
        for key in (
            "final_package_preview_revision_ref",
            "final_package_preview_ref",
            "working_preview_ref",
            "selected_artifacts",
            "scope_summaries",
            "scope_results",
            "external_dependency_count",
            "external_dependencies",
            "closure_dimension_statuses",
            "closure_dimensions",
            "upstream_correction_count",
            "upstream_correction_summaries",
            "upstream_corrections",
            "correction_lane_advisory",
            "publish_ready_candidate",
            "preview_ready_summary",
            "recommended_publish_request",
            "finalization_status",
            "selected_lineage",
            "correction_summary",
        )
        if outputs.get(key) is not None
    }
    if (
        top_level.get("selected_artifacts")
        or top_level.get("scope_summaries")
        or top_level.get("scope_results")
        or top_level.get("preview_ready_summary")
        or top_level.get("recommended_publish_request")
        or top_level.get("working_preview_ref")
    ):
        preview_ref = outputs.get("final_package_preview_revision_ref") or outputs.get(
            "final_package_preview_ref"
        )
        lines.extend(
            render_final_package_preview_timeline_lines(
                top_level,
                preview_ref=str(preview_ref) if preview_ref else None,
                indent=indent,
            )
        )

    results = outputs.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, Mapping):
                continue
            if item.get("artifact_type") != "deed_to_ir_final_package_preview":
                continue
            ref = item.get("ref_id") or item.get("final_package_preview_revision_ref")
            lines.extend(
                render_final_package_preview_timeline_lines(
                    item,
                    preview_ref=str(ref) if ref else None,
                    indent=indent,
                )
            )
    advisory = outputs.get("correction_lane_advisory")
    if isinstance(advisory, Mapping):
        body = "\n".join(lines)
        if "correction_lane_advisory:" not in body:
            lines.extend(render_correction_lane_advisory_timeline_lines(advisory, indent=indent))
    refusal_lines = render_upstream_corrections_required_timeline_lines(outputs, indent=indent)
    if refusal_lines:
        body = "\n".join(lines)
        if "upstream_corrections_required:" not in body:
            lines.extend(refusal_lines)
    shell_lines = render_retry_package_shell_timeline_lines(outputs.get("retry_package_shell"), indent=indent)
    if shell_lines:
        body = "\n".join(lines)
        if "retry_package_shell:" not in body:
            lines.extend(shell_lines)
    return lines
