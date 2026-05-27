"""Timeline rendering helpers for generic delegated subtasks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from harness.audit.artifact_ref_links import (
    ArtifactLinkContext,
    format_ref_with_link,
    inline_cap_notice,
    maybe_inline_thumbnail,
    resolve_artifact_image_link,
)
from harness.runtime.orchestration.subtasks.projection import project_subtask_output, task_excerpt

_MAX_JSON_TEXT = 1_200
_DELEGATE_PROMPT_MAX_CHARS = 400
_DELEGATE_RESULT_FIELD_MAX_CHARS = 320


def render_delegate_subtask_request(
    inputs: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None = None,
) -> list[str]:
    return render_delegate_subtask_section(
        alias=str(inputs.get("subtask_id") or "").strip() or None,
        inputs=inputs,
        item=None,
        link_context=link_context,
        include_result=False,
    )


def render_delegate_subtask_result(
    item: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None = None,
) -> list[str]:
    inputs = _coerce_mapping(item.get("action_inputs"))
    return render_delegate_subtask_section(
        alias=str(item.get("alias") or "").strip() or None,
        inputs=inputs,
        item=item,
        link_context=link_context,
        include_request=False,
    )


def render_delegate_subtask_section(
    *,
    alias: str | None,
    inputs: Mapping[str, Any],
    item: Mapping[str, Any] | None,
    link_context: ArtifactLinkContext | None = None,
    include_request: bool = True,
    include_result: bool = True,
) -> list[str]:
    projected = _projected_subtask(item)
    subtask_id = (
        str(projected.get("subtask_id") or "").strip()
        if projected
        else str(alias or inputs.get("subtask_id") or "").strip()
    )
    header_id = subtask_id or alias or "?"
    lines: list[str] = [f"Delegate subtask `{header_id}`"]

    profile = str(
        (projected or {}).get("profile") or inputs.get("profile") or ""
    ).strip()
    if profile:
        lines.append(f"- profile: `{profile}`")

    status = str((projected or {}).get("status") or "").strip()
    if status:
        lines.append(f"- status: {status}")
    elif item is not None:
        exec_state = str(item.get("execution_state") or "").strip()
        if exec_state:
            lines.append(f"- status: {exec_state}")

    if include_request:
        refs = inputs.get("context_refs")
        if isinstance(refs, list) and refs:
            lines.append("- context refs:")
            for ref in refs[:8]:
                ref_text = str(ref or "").strip()
                if not ref_text:
                    continue
                lines.append(f"  - {_render_context_ref(ref_text, link_context)}")
                if link_context is not None and ref_text.startswith("image:"):
                    link = resolve_artifact_image_link(ref_text, link_context, link_label="open crop")
                    inline = maybe_inline_thumbnail(
                        ref_text,
                        link,
                        link_context,
                        alt=f"delegate context {ref_text}",
                    )
                    for thumb in inline:
                        lines.append(f"    {thumb}")
        task = task_excerpt(inputs)
        if task:
            lines.append("- prompt:")
            lines.extend(_blockquote_excerpt(task, max_chars=_DELEGATE_PROMPT_MAX_CHARS))

    if include_result and projected:
        lines.extend(_render_projected_result(projected, link_context=link_context))

    if item is not None and include_result and not projected:
        reason = item.get("reason_code")
        if reason:
            lines.append(f"- execution_reason_code: {reason}")

    if link_context is not None:
        notice = inline_cap_notice(link_context)
        if notice:
            lines.append(notice)

    return lines


def _render_context_ref(ref_id: str, link_context: ArtifactLinkContext | None) -> str:
    if link_context is None or not ref_id.startswith("image:"):
        return f"`{ref_id}`"
    link = resolve_artifact_image_link(ref_id, link_context, link_label="open crop")
    return format_ref_with_link(ref_id, link, link_label="open crop")


def _render_projected_result(
    projected: Mapping[str, Any],
    *,
    link_context: ArtifactLinkContext | None,
) -> list[str]:
    lines: list[str] = ["- result:"]
    if projected.get("result_truncated") is True:
        lines.append("  - result_truncated: true")
        truncated_fields = projected.get("truncated_fields")
        if isinstance(truncated_fields, list) and truncated_fields:
            lines.append("  - truncated_fields:")
            for field in truncated_fields[:8]:
                lines.append(f"    - {field}")
        original_chars = projected.get("original_result_chars")
        if original_chars is not None:
            lines.append(f"  - original_result_chars: {original_chars}")

    input_refs = projected.get("input_refs")
    if isinstance(input_refs, list) and input_refs:
        lines.append("  - input_refs:")
        for ref in input_refs[:8]:
            ref_text = str(ref or "").strip()
            if ref_text:
                lines.append(f"    - {_render_context_ref(ref_text, link_context)}")

    result = projected.get("result") if isinstance(projected.get("result"), Mapping) else {}
    lines.extend(_render_result_fields(result, indent="  "))
    errors = projected.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("  - errors:")
        for row in errors[:4]:
            if isinstance(row, Mapping):
                reason = row.get("reason_code") or row
                message = row.get("message")
                if message:
                    lines.append(f"    - {reason}: {message}")
                else:
                    lines.append(f"    - {reason}")
            else:
                lines.append(f"    - {row}")
    trace = projected.get("subtask_trace")
    if isinstance(trace, Mapping) and trace:
        lines.append(f"  - subtask_trace: {_bounded_mapping_text(trace)}")
    return lines


def _projected_subtask(item: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if item is None:
        return None
    projected = item.get("delegate_subtask")
    if isinstance(projected, Mapping):
        return projected
    outputs = item.get("outputs_excerpt")
    return project_subtask_output(outputs if isinstance(outputs, Mapping) else None)


def _render_result_fields(result: Mapping[str, Any], *, indent: str) -> list[str]:
    lines: list[str] = []
    for key, value in result.items():
        if value is None:
            continue
        if isinstance(value, list):
            if not value:
                continue
            lines.append(f"{indent}- {key}:")
            for row in value[:4]:
                lines.append(f"{indent}  - {_bound_scalar(row)}")
            continue
        if isinstance(value, Mapping):
            nested = _render_result_fields(value, indent=f"{indent}  ")
            if nested:
                lines.append(f"{indent}- {key}:")
                lines.extend(nested)
            continue
        text = _bound_scalar(value)
        if text:
            lines.append(f"{indent}- {key}: `{text}`")
    return lines


def _blockquote_excerpt(text: str, *, max_chars: int) -> list[str]:
    bounded = _bound_scalar(text, max_chars=max_chars)
    if not bounded:
        return []
    wrapped = bounded.splitlines() or [bounded]
    return [f"  > {line}" if line else "  >" for line in wrapped[:6]]


def _bound_scalar(value: Any, *, max_chars: int = _DELEGATE_RESULT_FIELD_MAX_CHARS) -> str:
    text = str(value).strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


def _bounded_mapping_text(value: Mapping[str, Any]) -> str:
    import json

    text = json.dumps(dict(value), ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= _MAX_JSON_TEXT:
        return text
    return text[:_MAX_JSON_TEXT]


def _coerce_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
