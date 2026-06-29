"""Generic action-batch validation, policy checks, and bounded result projection."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .tool_batch_policy import (
    ALLOWED_SIDE_EFFECT_CLASSES,
    DomainActionBatchPolicy,
    ToolBatchPolicy,
    effective_max_batch_size,
    effective_max_resolved_actions,
    effective_tool_cap,
)
from .hydrate_next import PLACEHOLDER_OUTPUT_KEYS
from .subtasks.contracts import DELEGATE_SUBTASK_ACTION_TYPE
from .subtasks.projection import project_subtask_output

DEFAULT_MAX_BATCH_SIZE = 5
DEFAULT_MAX_RESOLVED_ACTIONS = 5
# Homogeneous delegate waves may retain up to the transcript-edit visual cap.
MAX_HOMOGENEOUS_DELEGATE_SEQUENCE_RESULT_ITEMS = 15
MAX_ACTION_INPUTS_JSON_CHARS_PER_ITEM = 12_000
MAX_TOTAL_ACTION_INPUTS_JSON_CHARS = 36_000
MAX_ALIAS_LEN = 64
_ALIAS_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")

_MAX_OUTPUTS_EXCERPT_CHARS = 800
_MAX_ARTIFACT_REFS_PER_ITEM = 8
_MAX_IMAGE_EVIDENCE_SUMMARY_REFS = 8
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")


@dataclass(frozen=True)
class ActionBatchItem:
    alias: str
    action_type: str
    action_inputs: dict[str, Any]


class ActionBatchValidationError(ValueError):
    """Raised when an action_batch payload fails mechanical validation."""


def _json_char_len(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), default=str))


def validate_alias(alias: str) -> None:
    if not alias or len(alias) > MAX_ALIAS_LEN:
        raise ActionBatchValidationError(
            f"action_batch alias must be 1..{MAX_ALIAS_LEN} chars"
        )
    if "." in alias:
        raise ActionBatchValidationError("action_batch alias must not contain '.'")
    if not _ALIAS_RE.match(alias):
        raise ActionBatchValidationError(
            "action_batch alias must match ^[a-zA-Z][a-zA-Z0-9_-]{0,63}$"
        )


def normalize_action_batch_items(raw: Any) -> tuple[ActionBatchItem, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, (list, tuple)):
        raise ActionBatchValidationError("action_batch must be a JSON array")
    if len(raw) < 1:
        raise ActionBatchValidationError("action_batch must be non-empty when present")
    items: list[ActionBatchItem] = []
    seen_aliases: set[str] = set()
    total_input_chars = 0
    for index, row in enumerate(raw):
        if not isinstance(row, Mapping):
            raise ActionBatchValidationError(f"action_batch[{index}] must be an object")
        alias_raw = row.get("alias")
        if not isinstance(alias_raw, str):
            raise ActionBatchValidationError(f"action_batch[{index}].alias is required")
        alias = alias_raw.strip()
        validate_alias(alias)
        if alias in seen_aliases:
            raise ActionBatchValidationError(f"duplicate action_batch alias: {alias}")
        seen_aliases.add(alias)
        action_type_raw = row.get("action_type")
        if not isinstance(action_type_raw, str) or not action_type_raw.strip():
            raise ActionBatchValidationError(
                f"action_batch[{index}].action_type is required"
            )
        action_type = action_type_raw.strip()
        inputs_raw = row.get("action_inputs")
        if inputs_raw is None:
            inputs: dict[str, Any] = {}
        elif isinstance(inputs_raw, Mapping):
            inputs = dict(inputs_raw)
        else:
            raise ActionBatchValidationError(
                f"action_batch[{index}].action_inputs must be an object"
            )
        item_chars = _json_char_len(inputs)
        if item_chars > MAX_ACTION_INPUTS_JSON_CHARS_PER_ITEM:
            raise ActionBatchValidationError(
                f"action_batch[{index}].action_inputs exceeds per-item JSON size cap"
            )
        total_input_chars += item_chars
        if total_input_chars > MAX_TOTAL_ACTION_INPUTS_JSON_CHARS:
            raise ActionBatchValidationError(
                "action_batch total action_inputs JSON size exceeds cap"
            )
        items.append(ActionBatchItem(alias=alias, action_type=action_type, action_inputs=inputs))
    return tuple(items)


def validate_action_batch_policy(
    items: tuple[ActionBatchItem, ...],
    *,
    available_tool_ids: tuple[str, ...],
    tool_batch_policies: Mapping[str, ToolBatchPolicy],
    domain_batch_policy: DomainActionBatchPolicy | None,
) -> None:
    if not items:
        return
    max_batch = effective_max_batch_size(
        global_default=DEFAULT_MAX_BATCH_SIZE,
        domain_policy=domain_batch_policy,
    )
    max_resolved = effective_max_resolved_actions(
        global_default=DEFAULT_MAX_RESOLVED_ACTIONS,
        domain_policy=domain_batch_policy,
    )
    if len(items) > max_batch:
        raise ActionBatchValidationError(
            f"action_batch exceeds max batch size {max_batch}"
        )
    if len(items) > max_resolved:
        raise ActionBatchValidationError(
            f"action_batch exceeds max resolved actions {max_resolved}"
        )

    per_tool_counts: dict[str, int] = {}
    side_effect_classes: set[str] = set()

    for item in items:
        if available_tool_ids and item.action_type not in available_tool_ids:
            raise ActionBatchValidationError(f"unknown action_batch action_type: {item.action_type}")
        policy = tool_batch_policies.get(item.action_type)
        if policy is None or not policy.allowed:
            raise ActionBatchValidationError(
                f"action_type not batchable: {item.action_type}"
            )
        side_effect_classes.add(policy.side_effect_class)
        if policy.side_effect_class not in ALLOWED_SIDE_EFFECT_CLASSES:
            raise ActionBatchValidationError(
                f"action_batch side_effect_class not allowed: {policy.side_effect_class}"
            )
        per_tool_counts[item.action_type] = per_tool_counts.get(item.action_type, 0) + 1
        tool_cap = effective_tool_cap(
            tool_id=item.action_type,
            tool_policy=policy,
            global_default=max_batch,
            domain_policy=domain_batch_policy,
        )
        if per_tool_counts[item.action_type] > tool_cap:
            raise ActionBatchValidationError(
                f"action_batch exceeds per-tool cap for {item.action_type} ({tool_cap})"
            )

    if len(side_effect_classes) > 1:
        raise ActionBatchValidationError(
            "action_batch cannot mix disallowed side_effect classes"
        )


def summarize_image_evidence_for_projection(
    image_evidence: list[Any] | tuple[Any, ...] | None,
) -> dict[str, Any] | None:
    """Mechanical summary only — never include ``b64`` (pixels use ``pending_image_evidence``)."""
    if not image_evidence:
        return None
    ref_ids: list[str] = []
    media_types: list[str] = []
    count = 0
    for row in image_evidence:
        if not isinstance(row, Mapping):
            continue
        count += 1
        ref_id = row.get("ref_id")
        if isinstance(ref_id, str) and ref_id.strip() and ref_id.strip() not in ref_ids:
            ref_ids.append(ref_id.strip())
        media_type = row.get("media_type")
        if isinstance(media_type, str) and media_type.strip() and media_type.strip() not in media_types:
            media_types.append(media_type.strip())
        if count >= _MAX_IMAGE_EVIDENCE_SUMMARY_REFS:
            break
    if count < 1:
        return None
    summary: dict[str, Any] = {"count": count}
    if ref_ids:
        summary["ref_ids"] = ref_ids[:_MAX_IMAGE_EVIDENCE_SUMMARY_REFS]
    if media_types:
        summary["media_types"] = media_types[:_MAX_IMAGE_EVIDENCE_SUMMARY_REFS]
    return summary


def project_batch_item_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Prompt/audit-safe projection of one batch item row (no raw image bytes)."""
    out: dict[str, Any] = {
        "alias": str(row.get("alias") or ""),
        "action_type": str(row.get("action_type") or ""),
        "execution_state": str(row.get("execution_state") or ""),
    }
    artifact_refs = row.get("artifact_refs")
    if isinstance(artifact_refs, (list, tuple)) and artifact_refs:
        out["artifact_refs"] = [
            str(x) for x in artifact_refs if isinstance(x, str) and x.strip()
        ][:_MAX_ARTIFACT_REFS_PER_ITEM]
    delegate_result_ref = row.get("delegate_result_ref")
    if isinstance(delegate_result_ref, str) and delegate_result_ref.strip():
        out["delegate_result_ref"] = delegate_result_ref.strip()
    outputs_excerpt = row.get("outputs_excerpt")
    if isinstance(outputs_excerpt, Mapping) and outputs_excerpt:
        subtask_projection = project_subtask_output(outputs_excerpt)
        if subtask_projection:
            out["delegate_subtask"] = subtask_projection
        else:
            out["outputs_excerpt"] = _bounded_outputs_excerpt(outputs_excerpt)
    crop_summary = row.get("point_crop_set_summary")
    if isinstance(crop_summary, Mapping) and crop_summary:
        out["point_crop_set_summary"] = dict(crop_summary)
    source_window = row.get("source_window")
    if isinstance(source_window, Mapping) and source_window:
        out["source_window"] = dict(source_window)
    compact_outputs = _compact_outputs_for_projection(
        outputs_excerpt if isinstance(outputs_excerpt, Mapping) else None,
        crop_summary if isinstance(crop_summary, Mapping) else None,
    )
    if compact_outputs:
        out["outputs"] = compact_outputs
    read_summary = row.get("read_action_summary")
    if isinstance(read_summary, Mapping) and read_summary:
        out["read_action_summary"] = dict(read_summary)
    error = row.get("error")
    if isinstance(error, Mapping) and error:
        out["error"] = dict(error)
    summary = row.get("image_evidence_summary")
    if isinstance(summary, Mapping) and summary:
        out["image_evidence_summary"] = dict(summary)
    elif row.get("image_evidence") is not None:
        legacy_summary = summarize_image_evidence_for_projection(
            row.get("image_evidence") if isinstance(row.get("image_evidence"), (list, tuple)) else ()
        )
        if legacy_summary:
            out["image_evidence_summary"] = legacy_summary
    return out


def build_batch_tool_request_summary(action_plan: Any) -> dict[str, Any]:
    """Bounded audit/lifecycle request shape for an ``action_batch`` turn."""
    items = getattr(action_plan, "action_batch", ()) or ()
    return {
        "action_batch": [
            {
                "alias": item.alias,
                "action_type": item.action_type,
                "action_inputs": dict(item.action_inputs),
            }
            for item in items
        ],
        "idempotency_key": str(getattr(action_plan, "idempotency_key", "") or ""),
        "skip_execution": bool(getattr(action_plan, "skip_execution", False)),
        "wait_for_human": bool(getattr(action_plan, "wait_for_human", False)),
        "complete_run": bool(getattr(action_plan, "complete_run", False)),
        "rationale": getattr(action_plan, "rationale", None),
    }


def sequence_result_items_cap(items: list[Any] | tuple[Any, ...]) -> int:
    """Bounded retention cap for ``recent_action_sequence_result.items``."""

    if not items:
        return DEFAULT_MAX_BATCH_SIZE
    if all(
        isinstance(row, Mapping)
        and str(row.get("action_type") or "") == DELEGATE_SUBTASK_ACTION_TYPE
        for row in items
    ):
        return MAX_HOMOGENEOUS_DELEGATE_SEQUENCE_RESULT_ITEMS
    return DEFAULT_MAX_BATCH_SIZE


def bound_sequence_result_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return items[: sequence_result_items_cap(items)]


def build_batch_tool_result_summary(batch_result: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Bounded audit/lifecycle result shape for an ``action_batch`` turn."""
    if not batch_result:
        return None
    items_raw = batch_result.get("items")
    if not isinstance(items_raw, (list, tuple)):
        return None
    items = [
        project_batch_item_row(row)
        for row in items_raw
        if isinstance(row, Mapping)
    ]
    return {
        "batch_id": str(batch_result.get("batch_id") or ""),
        "source_turn_index": int(batch_result.get("source_turn_index") or 0),
        "items": bound_sequence_result_items(items),
    }


def validate_stored_action_batch_result(row: Any) -> dict[str, Any] | None:
    """Resume-snapshot validator; strips any legacy raw ``image_evidence`` payloads."""
    if row is None or not isinstance(row, Mapping):
        return None
    batch_id = str(row.get("batch_id") or "").strip()
    if not batch_id:
        return None
    try:
        source_turn_index = int(row.get("source_turn_index", 0))
    except (TypeError, ValueError):
        return None
    if source_turn_index < 0:
        return None
    items_raw = row.get("items")
    if not isinstance(items_raw, (list, tuple)) or len(items_raw) < 1:
        return None
    items: list[dict[str, Any]] = []
    for entry in items_raw[: sequence_result_items_cap(items_raw)]:
        if not isinstance(entry, Mapping):
            return None
        alias = str(entry.get("alias") or "").strip()
        action_type = str(entry.get("action_type") or "").strip()
        execution_state = str(entry.get("execution_state") or "").strip()
        if not alias or not action_type or not execution_state:
            return None
        try:
            validate_alias(alias)
        except ActionBatchValidationError:
            return None
        items.append(project_batch_item_row(entry))
    return {
        "batch_id": batch_id,
        "source_turn_index": source_turn_index,
        "items": items,
    }


def _bounded_outputs_excerpt(outputs: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(outputs, Mapping) or not outputs:
        return {}
    safe_outputs = _strip_binary(dict(outputs))
    text = json.dumps(safe_outputs, separators=(",", ":"), default=str)
    if len(text) <= _MAX_OUTPUTS_EXCERPT_CHARS:
        return dict(safe_outputs)
    preserved = {
        key: safe_outputs[key]
        for key in PLACEHOLDER_OUTPUT_KEYS
        if key in safe_outputs
    }
    if str(safe_outputs.get("sub_action") or "").strip():
        preserved["sub_action"] = str(safe_outputs.get("sub_action")).strip()
    overlay_role = safe_outputs.get("overlay_role")
    if isinstance(overlay_role, str) and overlay_role.strip():
        preserved["overlay_role"] = overlay_role.strip()
    return {
        "_truncated": True,
        "preview": text[:_MAX_OUTPUTS_EXCERPT_CHARS],
        **preserved,
    }


def _strip_binary(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, inner in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _BINARY_KEY_PARTS):
                continue
            out[str(key)] = _strip_binary(inner)
        return out
    if isinstance(value, list):
        return [_strip_binary(item) for item in value]
    if isinstance(value, tuple):
        return [_strip_binary(item) for item in value]
    return value


def _delegate_outputs_excerpt(
    outputs: Mapping[str, Any],
    *,
    projected: Mapping[str, Any],
) -> dict[str, Any]:
    excerpt: dict[str, Any] = {
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "subtask_id": projected.get("subtask_id"),
        "profile": projected.get("profile"),
        "status": projected.get("status"),
        "target_entity_id": projected.get("target_entity_id"),
        "input_refs": projected.get("input_refs"),
        "result": projected.get("result"),
    }
    for key in ("result_truncated", "truncated_fields", "original_result_chars", "errors", "subtask_trace"):
        if key in projected:
            excerpt[key] = projected[key]
        elif key in outputs:
            excerpt[key] = outputs[key]
    return {key: value for key, value in excerpt.items() if value is not None}


def _delegate_result_audit(outputs: Mapping[str, Any]) -> dict[str, Any]:
    result = outputs.get("result")
    if not isinstance(result, Mapping):
        return {}
    audit: dict[str, Any] = {}
    for key, value in result.items():
        if value is None:
            continue
        if isinstance(value, str):
            text = value.strip()
            if text:
                audit[str(key)] = text[:4_000]
            continue
        if isinstance(value, list):
            rows = [str(item)[:1_000] for item in value[:8] if item is not None]
            if rows:
                audit[str(key)] = rows
            continue
        if isinstance(value, (int, float, bool)):
            audit[str(key)] = value
            continue
        text = str(value).strip()
        if text:
            audit[str(key)] = text[:1_000]
    return audit


def build_batch_item_result_row(
    *,
    alias: str,
    action_type: str,
    execution_state: str,
    outputs: Mapping[str, Any] | None = None,
    artifact_refs: list[str] | tuple[str, ...] | None = None,
    image_evidence: list[Any] | None = None,
    error: Mapping[str, Any] | None = None,
    delegate_result_ref: str | None = None,
    action_inputs: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "alias": alias,
        "action_type": action_type,
        "execution_state": execution_state,
    }
    if artifact_refs:
        row["artifact_refs"] = list(artifact_refs)[:_MAX_ARTIFACT_REFS_PER_ITEM]
    if delegate_result_ref:
        row["delegate_result_ref"] = str(delegate_result_ref)
    if action_type == DELEGATE_SUBTASK_ACTION_TYPE and isinstance(outputs, Mapping):
        subtask_projection = project_subtask_output(outputs)
        if subtask_projection:
            row["delegate_subtask"] = subtask_projection
            audit_result = _delegate_result_audit(outputs)
            if audit_result:
                row["delegate_result_audit"] = audit_result
            row["outputs_excerpt"] = _delegate_outputs_excerpt(outputs, projected=subtask_projection)
        else:
            excerpt = _bounded_outputs_excerpt(outputs)
            if excerpt:
                row["outputs_excerpt"] = excerpt
    else:
        excerpt = _bounded_outputs_excerpt(outputs)
        if excerpt:
            row["outputs_excerpt"] = excerpt
    if isinstance(outputs, Mapping):
        from harness.runtime.memory.point_crop_set_projection import (
            project_point_crop_set_summary,
        )

        crop_summary = project_point_crop_set_summary(outputs)
        if crop_summary:
            row["point_crop_set_summary"] = crop_summary
        from tooling.mapping.transcript_edit.source_window import compact_source_window_for_projection

        source_window = compact_source_window_for_projection(outputs.get("source_window"))
        if source_window:
            row["source_window"] = source_window
    evidence_summary = summarize_image_evidence_for_projection(image_evidence)
    if evidence_summary:
        row["image_evidence_summary"] = evidence_summary
    if error:
        row["error"] = dict(error)
    if isinstance(outputs, Mapping):
        from tooling.mapping.deed_to_ir.read_action_projection import compact_read_action_summary

        read_summary = compact_read_action_summary(
            action_type,
            outputs,
            action_inputs=action_inputs,
        )
        if read_summary:
            row["read_action_summary"] = read_summary
    return row


def build_action_batch_result_record(
    *,
    batch_id: str,
    items: list[dict[str, Any]],
    source_turn_index: int,
) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "source_turn_index": int(source_turn_index),
        "items": bound_sequence_result_items(items),
    }


def _compact_outputs_for_projection(
    outputs_excerpt: Mapping[str, Any] | None,
    crop_summary: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Bounded transform outputs for prompt/placeholder visibility."""
    compact: dict[str, Any] = {}
    if isinstance(outputs_excerpt, Mapping):
        for key in ("derived_ref_id", "overlay_role", "sub_action", "source_window"):
            value = outputs_excerpt.get(key)
            if isinstance(value, str) and value.strip():
                compact[key] = value.strip()
            elif isinstance(value, Mapping) and value:
                compact[key] = dict(value)
    if isinstance(crop_summary, Mapping):
        from harness.runtime.memory.point_crop_set_projection import (
            compact_crop_identity_from_summary,
        )

        for key, value in compact_crop_identity_from_summary(crop_summary).items():
            compact.setdefault(key, value)
    return compact or None


def build_batch_results_snapshot(
    batch_result: Mapping[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    """Map alias → tool-result snapshot for per-row ``@this.*`` hydrate_next resolution."""
    from .hydrate_next import build_tool_result_snapshot_from_batch_item

    if not batch_result:
        return {}
    items = batch_result.get("items")
    if not isinstance(items, (list, tuple)):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in items:
        if not isinstance(row, Mapping):
            continue
        alias = str(row.get("alias") or "").strip()
        if not alias:
            continue
        out[alias] = build_tool_result_snapshot_from_batch_item(row)
    return out
