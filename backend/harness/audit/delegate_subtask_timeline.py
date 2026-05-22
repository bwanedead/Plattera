"""Timeline rendering helpers for generic delegated subtasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.runtime.orchestration.subtasks.projection import project_subtask_output, task_excerpt

_MAX_JSON_TEXT = 1_200


def render_delegate_subtask_request(inputs: Mapping[str, Any]) -> list[str]:
    lines: list[str] = []
    profile = str(inputs.get("profile") or "").strip()
    if profile:
        lines.append(f"      subtask_profile: {profile}")
    excerpt = task_excerpt(inputs)
    if excerpt:
        lines.append(f"      subtask_task_excerpt: {excerpt}")
    refs = inputs.get("context_refs")
    if isinstance(refs, list) and refs:
        lines.append("      subtask_input_refs:")
        for ref in refs[:8]:
            lines.append(f"        - {ref}")
    isolation = inputs.get("isolation")
    if isinstance(isolation, Mapping) and isolation:
        lines.append(f"      subtask_isolation: {_bounded_mapping_text(isolation)}")
    return lines


def render_delegate_subtask_result(item: Mapping[str, Any]) -> list[str]:
    projected = item.get("delegate_subtask") if isinstance(item.get("delegate_subtask"), Mapping) else None
    if not projected:
        outputs = item.get("outputs_excerpt")
        projected = project_subtask_output(outputs if isinstance(outputs, Mapping) else None)
    if not projected:
        return []
    lines = ["      subtask_result:"]
    for key in ("profile", "status"):
        value = projected.get(key)
        if value:
            lines.append(f"        {key}: {value}")
    input_refs = projected.get("input_refs")
    if isinstance(input_refs, list) and input_refs:
        lines.append("        input_refs:")
        for ref in input_refs[:8]:
            lines.append(f"          - {ref}")
    result = projected.get("result") if isinstance(projected.get("result"), Mapping) else {}
    lines.extend(_render_result_fields(result, indent="        "))
    errors = projected.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("        errors:")
        for row in errors[:4]:
            if isinstance(row, Mapping):
                lines.append(f"          - {row.get('reason_code') or row}")
            else:
                lines.append(f"          - {row}")
    trace = projected.get("subtask_trace")
    if isinstance(trace, Mapping) and trace:
        lines.append(f"        subtask_trace: {_bounded_mapping_text(trace)}")
    return lines


def _render_result_fields(result: Mapping[str, Any], *, indent: str) -> list[str]:
    lines: list[str] = []
    for key, value in result.items():
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{indent}{key}:")
            for row in value[:4]:
                lines.append(f"{indent}  - {row}")
            continue
        if isinstance(value, Mapping):
            nested = _render_result_fields(value, indent=f"{indent}  ")
            if nested:
                lines.append(f"{indent}{key}:")
                lines.extend(nested)
            continue
        text = str(value).strip()
        if text:
            lines.append(f"{indent}{key}: {text}")
    return lines


def _bounded_mapping_text(value: Mapping[str, Any]) -> str:
    import json

    text = json.dumps(dict(value), ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= _MAX_JSON_TEXT:
        return text
    return text[:_MAX_JSON_TEXT]
