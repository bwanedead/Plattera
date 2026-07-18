"""Deed-to-IR draft (save/patch) AgentResultView builders."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from tooling.mapping.deed_to_ir.draft_ir_lifecycle import compact_current_draft_ir_for_projection

from .result_view_common import (
    bound_message,
    bound_text,
    copy_scalar_fields,
    fit_payload_collections,
    mapping_rows,
    try_build_view,
)

SCHEMA_SAVE_IR_ARTIFACT = "deed_to_ir.save_ir_artifact.v1"
SCHEMA_PATCH_IR_DRAFT = "deed_to_ir.patch_ir_draft.v1"

_DRAFT_IDENTITY_KEYS = (
    "ir_artifact_ref",
    "draft_ir_ref",
    "working_draft_ref",
    "base_draft_ref",
    "parent_draft_ref",
    "draft_version",
    "draft_sequence_index",
    "graph_id",
    "artifact_id",
    "is_draft",
    "node_count",
    "edge_count",
    "course_count",
    "unknown_node_count",
    "compile_gap_count",
    "judge_finding_count",
    "mechanically_mappable_candidate",
    "mapping_submission_ready_candidate",
    "draft_quality_flags",
    "compile_artifact_ref",
    "judge_artifact_ref",
    # Optional patch outcome scalars when present on the raw result.
    "node_upserts_applied",
    "edge_upserts_applied",
    "node_removals_applied",
    "edge_removals_applied",
    "course_updates_applied",
    "patch_ops_applied",
)

_COMPACT_COLLECTION_KEYS = (
    "nodes",
    "edges",
    "compile_gaps",
    "judge_findings",
    "draft_repair_items",
)


def build_save_ir_artifact_view(
    outputs: Mapping[str, Any],
    *,
    continuity_key: str | None,
):
    return _build_draft_view(
        outputs,
        schema_id=SCHEMA_SAVE_IR_ARTIFACT,
        continuity_key=continuity_key,
    )


def build_patch_ir_draft_view(
    outputs: Mapping[str, Any],
    *,
    continuity_key: str | None,
):
    return _build_draft_view(
        outputs,
        schema_id=SCHEMA_PATCH_IR_DRAFT,
        continuity_key=continuity_key,
    )


def _build_draft_view(
    outputs: Mapping[str, Any],
    *,
    schema_id: str,
    continuity_key: str | None,
):
    base = copy_scalar_fields(outputs, _DRAFT_IDENTITY_KEYS)
    current_ref = (
        outputs.get("working_draft_ref")
        or outputs.get("ir_artifact_ref")
        or outputs.get("draft_ir_ref")
    )
    if isinstance(current_ref, str) and current_ref.strip():
        base["current_ir_artifact_ref"] = current_ref.strip()

    parent_ref = outputs.get("parent_draft_ref") or outputs.get("base_draft_ref")
    if isinstance(parent_ref, str) and parent_ref.strip():
        base["parent_draft_ref"] = parent_ref.strip()
        if "base_draft_ref" not in base and outputs.get("base_draft_ref"):
            base["base_draft_ref"] = str(outputs["base_draft_ref"]).strip()

    current = outputs.get("current_draft_ir")
    if not isinstance(current, Mapping):
        current = outputs
    compact = compact_current_draft_ir_for_projection(
        current if isinstance(current, Mapping) else None
    )

    collections: dict[str, list[dict[str, Any]]] = {}
    intake_omitted: dict[str, int] = {}
    if compact is not None:
        scalar_draft = dict(compact)
        source_draft = current if isinstance(current, Mapping) else {}
        for key in _COMPACT_COLLECTION_KEYS:
            raw_rows = scalar_draft.pop(key, None)
            truncated_meta = scalar_draft.pop(f"{key}_truncated", None)
            row_list = raw_rows if isinstance(raw_rows, list) else []
            valid_in_compact = sum(1 for item in row_list if isinstance(item, Mapping))
            pre_total = _pre_compaction_total(
                key,
                valid_in_compact=valid_in_compact,
                truncated_meta=truncated_meta,
                scalar_draft=scalar_draft,
                source_draft=source_draft,
            )
            pre_omissions = max(0, (pre_total or valid_in_compact) - valid_in_compact)
            rows, cap_omissions = mapping_rows(row_list)
            combined_omissions = pre_omissions + cap_omissions
            if rows or combined_omissions:
                collections[key] = rows
                intake_omitted[key] = combined_omissions
        warning = scalar_draft.get("evaluation_warning")
        if isinstance(warning, Mapping):
            scalar_draft["evaluation_warning"] = _bound_evaluation_warning(warning)
        base["current_draft_ir"] = scalar_draft

    if "evaluation_warning" in outputs and isinstance(outputs.get("evaluation_warning"), Mapping):
        if "evaluation_warning" not in base.get("current_draft_ir", {}):
            base["evaluation_warning"] = _bound_evaluation_warning(outputs["evaluation_warning"])

    patch_rows, patch_omitted = mapping_rows(outputs.get("patch_warnings"))
    if patch_rows or patch_omitted:
        collections["patch_warnings"] = patch_rows
        intake_omitted["patch_warnings"] = patch_omitted

    validation_rows, validation_omitted = _validation_error_rows(outputs.get("validation_errors"))
    if validation_rows or validation_omitted:
        collections["validation_errors"] = validation_rows
        intake_omitted["validation_errors"] = validation_omitted

    if not collections:
        return try_build_view(
            schema_id=schema_id,
            payload=base,
            continuity_key=continuity_key,
        )
    return fit_payload_collections(
        schema_id=schema_id,
        continuity_key=continuity_key,
        base=base,
        collections=collections,
        intake_omitted=intake_omitted,
    )


def _bound_evaluation_warning(warning: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    code = warning.get("reason_code")
    if isinstance(code, str) and code.strip():
        out["reason_code"] = code.strip()
    msg = bound_message(warning.get("message"))
    if msg:
        out.update(msg)
    return out


def _pre_compaction_total(
    key: str,
    *,
    valid_in_compact: int,
    truncated_meta: Any,
    scalar_draft: Mapping[str, Any],
    source_draft: Mapping[str, Any],
) -> int | None:
    """Strongest mechanical evidence for the pre-compaction valid-row total."""
    truncated_total = None
    if isinstance(truncated_meta, int) and not isinstance(truncated_meta, bool) and truncated_meta >= 0:
        truncated_total = valid_in_compact + truncated_meta

    if key == "nodes":
        return _first_nonneg_int(
            scalar_draft.get("node_count"),
            source_draft.get("node_count"),
            _valid_mapping_count(source_draft.get("nodes")),
            truncated_total,
        )
    if key == "edges":
        return _first_nonneg_int(
            scalar_draft.get("edge_count"),
            source_draft.get("edge_count"),
            _valid_mapping_count(source_draft.get("edges")),
            truncated_total,
        )
    if key == "compile_gaps":
        return _first_nonneg_int(
            scalar_draft.get("compile_gap_count"),
            source_draft.get("compile_gap_count"),
            _valid_mapping_count(source_draft.get("compile_gaps")),
        )
    if key == "judge_findings":
        return _first_nonneg_int(
            scalar_draft.get("judge_finding_count"),
            source_draft.get("judge_finding_count"),
            _valid_mapping_count(source_draft.get("judge_findings")),
        )
    if key == "draft_repair_items":
        return _first_nonneg_int(_valid_mapping_count(source_draft.get("draft_repair_items")))
    return None


def _valid_mapping_count(raw: Any) -> int | None:
    if not isinstance(raw, list):
        return None
    return sum(1 for item in raw if isinstance(item, Mapping))


def _first_nonneg_int(*candidates: Any) -> int | None:
    for value in candidates:
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
            return value
    return None


def _validation_error_rows(raw: Any) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list):
        return [], 0
    normalized: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            msg = bound_text(item, field="message") or {}
            normalized.append(msg)
        elif isinstance(item, Mapping):
            row = dict(item)
            if "message" in row:
                msg = bound_text(row.get("message"), field="message")
                if msg:
                    row.pop("message", None)
                    row.update(msg)
                else:
                    row.pop("message", None)
            normalized.append(row)
    return mapping_rows(normalized)
