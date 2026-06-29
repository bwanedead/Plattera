"""Timeline and hydration projection helpers for deed-to-IR final package preview."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def build_recommended_publish_request(*, preview_revision_ref: str) -> dict[str, str]:
    return {"final_package_preview_ref": preview_revision_ref}


def compact_preview_row_summaries(
    *,
    scope_results: list[dict[str, Any]],
    external_dependencies: list[dict[str, Any]],
    closure_dimensions: list[dict[str, Any]],
    notes: list[dict[str, Any]],
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
    return {
        "scope_summaries": scope_summaries,
        "scope_result_count": len(scope_results),
        "external_dependency_count": len(external_dependencies),
        "closure_dimension_statuses": closure_dimension_statuses,
        "closure_dimension_count": len(closure_dimensions),
        "note_count": len(notes),
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
        "recommended_publish_request": build_recommended_publish_request(
            preview_revision_ref=preview_revision_ref,
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

    return lines


def render_final_package_preview_tool_output(
    outputs: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    """Render final package preview from prepare outputs or hydrate result rows."""
    if not isinstance(outputs, Mapping):
        return []
    lines: list[str] = []
    top_level = {
        key: outputs.get(key)
        for key in (
            "final_package_preview_revision_ref",
            "final_package_preview_ref",
            "selected_artifacts",
            "scope_summaries",
            "scope_results",
            "external_dependency_count",
            "external_dependencies",
            "closure_dimension_statuses",
            "closure_dimensions",
            "publish_ready_candidate",
        )
        if outputs.get(key) is not None
    }
    if top_level.get("selected_artifacts") or top_level.get("scope_summaries") or top_level.get(
        "scope_results"
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
    return lines
