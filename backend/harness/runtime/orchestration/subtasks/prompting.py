"""Compact child-prompt builder for delegated subtasks."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from .contracts import DelegateSubtaskRequest, HydratedSubtaskContext, SubtaskProfile

_MAX_REF_SUMMARY_CHARS = 1_200
_BINARY_KEY_PARTS = ("b64", "base64", "bytes", "binary")


def build_child_prompt(
    *,
    profile: SubtaskProfile,
    request: DelegateSubtaskRequest,
    context: HydratedSubtaskContext,
) -> str:
    """Build the isolated single-turn child prompt.

    This intentionally does not call the parent prompt builder.  It carries only
    profile framing, parent-authored task, supplied refs/media summaries, and the
    output contract.
    """

    prompt_body = {
        "profile": {
            "profile_id": profile.profile_id,
            "owner": profile.owner,
            "description": profile.description,
            "allowed_ref_kinds": list(profile.allowed_ref_kinds),
            "max_turns": profile.max_turns,
        },
        "task": request.task,
        "isolation": dict(request.isolation),
        "input_refs": list(context.input_refs),
        "supplied_ref_summaries": list(context.prompt_ref_summaries),
        "hydration_errors": list(context.errors),
        "media_attachments": [
            {
                "ref_id": str(row.get("ref_id") or ""),
                "media_type": str(row.get("media_type") or ""),
            }
            for row in context.image_attachments
            if isinstance(row, Mapping)
        ],
        "output_contract": dict(request.output_contract or {"kind": "observation"}),
        "required_json_shape": _bounded_schema(profile.result_schema),
    }
    safe_body = _strip_binary(prompt_body)
    body_json = json.dumps(safe_body, ensure_ascii=False, indent=2, default=str)
    return (
        f"{profile.prompt_preamble}\n\n"
        "Rules:\n"
        "- Perform only this isolated task.\n"
        "- Use only the supplied refs, summaries, and media attachments.\n"
        "- Do not infer from broader mission context or unsupplied candidates.\n"
        "- Do not include confidence fields.\n"
        "- Return one JSON object only.\n\n"
        f"Subtask packet:\n{body_json}\n"
    )


def _bounded_schema(schema: Mapping[str, Any]) -> Any:
    safe = _strip_binary(dict(schema or {}))
    text = json.dumps(safe, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= 2_000:
        return safe
    return {"_truncated": True, "preview": text[:2_000]}


def prompt_ref_summary(ref_id: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a bounded, prompt-safe ref summary."""

    safe = _strip_binary(dict(payload or {}))
    preview = json.dumps(safe, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(preview) > _MAX_REF_SUMMARY_CHARS:
        preview = preview[:_MAX_REF_SUMMARY_CHARS]
        return {
            "ref_id": ref_id,
            "truncated": True,
            "preview": preview,
        }
    return {
        "ref_id": ref_id,
        "truncated": False,
        "payload": safe,
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
