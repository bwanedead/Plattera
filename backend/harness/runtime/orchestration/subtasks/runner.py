"""Single-turn delegated subtask execution."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any

from services.llm.call_options import LlmCallOptions

from ....execution.contracts import ExecutionStepRequest
from .contracts import (
    DELEGATE_SUBTASK_ACTION_TYPE,
    SUBTASK_STATUSES,
    DelegateSubtaskRequest,
    HydratedSubtaskContext,
    SubtaskProfile,
)
from .prompting import build_child_prompt, prompt_ref_summary
from .result_schema import (
    SubtaskResultSchemaError,
    empty_result_for_profile,
    normalize_result_payload,
)

TextModelCaller = Callable[..., Mapping[str, Any] | str]
HydrationHandler = Callable[[Any], Any]

_MAX_FIELD_CHARS = 240


def run_delegate_subtask(
    *,
    subtask_id: str,
    request: DelegateSubtaskRequest,
    profile: SubtaskProfile,
    model_caller: TextModelCaller,
    default_model_name: str,
    hydration_handler: HydrationHandler | None,
    parent_request: ExecutionStepRequest,
) -> dict[str, Any]:
    """Execute one isolated child model call and return a bounded tool result."""

    context = resolve_context_refs(
        request=request,
        profile=profile,
        hydration_handler=hydration_handler,
        parent_request=parent_request,
    )
    prompt = build_child_prompt(profile=profile, request=request, context=context)
    model_name = profile.model_policy.model_name or default_model_name
    try:
        raw = model_caller(
            prompt,
            model_name,
            call_options=LlmCallOptions(
                output_mode="json_object",
                image_attachments=context.image_attachments,
                phase=profile.model_policy.phase or DELEGATE_SUBTASK_ACTION_TYPE,
            ),
        )
    except Exception as exc:  # noqa: BLE001 - model failures become bounded subtask failures
        return _failed_output(
            subtask_id=subtask_id,
            request=request,
            reason_code="subtask_model_call_failed",
            message=str(exc),
            prompt_char_count=len(prompt),
            model_name=model_name,
            image_attachment_count=len(context.image_attachments),
            hydration_errors=context.errors,
            profile=profile,
        )

    normalized = normalize_child_output(
        raw,
        subtask_id=subtask_id,
        request=request,
        profile=profile,
    )
    normalized["subtask_trace"] = {
        "model": model_name,
        "prompt_char_count": len(prompt),
        "image_attachment_count": len(context.image_attachments),
    }
    if context.errors:
        normalized.setdefault("errors", [])
        normalized["errors"] = list(normalized["errors"]) + [dict(row) for row in context.errors]
    return normalized


def resolve_context_refs(
    *,
    request: DelegateSubtaskRequest,
    profile: SubtaskProfile,
    hydration_handler: HydrationHandler | None,
    parent_request: ExecutionStepRequest,
) -> HydratedSubtaskContext:
    if hydration_handler is None:
        return HydratedSubtaskContext(
            input_refs=request.context_refs,
            prompt_ref_summaries=tuple(
                {
                    "ref_id": ref,
                    "truncated": False,
                    "payload": {"note": "No hydrate_artifact_refs handler was registered for this run."},
                }
                for ref in request.context_refs
            ),
            errors=(
                {
                    "reason_code": "hydration_handler_unavailable",
                    "message": "Context refs were passed by id only.",
                },
            ),
        )

    hydrate_request = ExecutionStepRequest(
        session_id=parent_request.session_id,
        action_id="hydrate_artifact_refs",
        inputs={"ref_ids": list(request.context_refs), "max_refs": len(request.context_refs)},
        idempotency_key=f"{parent_request.idempotency_key}:subtask_hydrate",
        run_id=parent_request.run_id,
    )
    try:
        raw = hydration_handler(hydrate_request)
    except Exception as exc:  # noqa: BLE001
        return HydratedSubtaskContext(
            input_refs=request.context_refs,
            errors=(
                {
                    "reason_code": "hydration_handler_failed",
                    "message": str(exc),
                },
            ),
        )

    outputs, image_evidence = _coerce_hydration_result(raw)
    if "image" not in set(profile.allowed_ref_kinds):
        image_evidence = ()
    results = outputs.get("results") if isinstance(outputs, Mapping) else None
    summaries: list[Mapping[str, Any]] = []
    if isinstance(results, (list, tuple)):
        for row in results:
            if not isinstance(row, Mapping):
                continue
            ref_id = str(row.get("ref_id") or row.get("ref") or "").strip()
            summaries.append(prompt_ref_summary(ref_id or "unknown", row))
    errors = outputs.get("errors") if isinstance(outputs, Mapping) else None
    error_rows = tuple(dict(row) for row in errors if isinstance(row, Mapping)) if isinstance(errors, list) else ()
    return HydratedSubtaskContext(
        input_refs=request.context_refs,
        prompt_ref_summaries=tuple(summaries),
        image_attachments=tuple(image_evidence),
        errors=error_rows,
    )


def normalize_child_output(
    raw: Mapping[str, Any] | str,
    *,
    subtask_id: str,
    request: DelegateSubtaskRequest,
    profile: SubtaskProfile,
) -> dict[str, Any]:
    parsed = _parse_raw_child_output(raw)
    if not isinstance(parsed, Mapping):
        return _failed_output(
            subtask_id=subtask_id,
            request=request,
            reason_code="subtask_output_malformed",
            message="Child output was not a JSON object.",
            profile=profile,
        )
    status = str(parsed.get("status") or "").strip()
    if status not in SUBTASK_STATUSES:
        return _failed_output(
            subtask_id=subtask_id,
            request=request,
            reason_code="subtask_status_invalid",
            message="Child output status was missing or invalid.",
            profile=profile,
        )
    result_raw = parsed.get("result")
    try:
        result, truncation = normalize_result_payload(
            result_raw if isinstance(result_raw, Mapping) else {},
            profile=profile,
        )
    except SubtaskResultSchemaError as exc:
        return _failed_output(
            subtask_id=subtask_id,
            request=request,
            reason_code=exc.reason_code,
            message=str(exc),
            profile=profile,
        )
    normalized = {
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "subtask_id": str(subtask_id or DELEGATE_SUBTASK_ACTION_TYPE),
        "profile": request.profile,
        "status": status,
        "input_refs": list(request.context_refs),
        "result": result,
        "result_schema": dict(profile.result_schema),
    }
    if truncation:
        normalized.update(truncation)
    if profile.result_validator is not None:
        try:
            profile.result_validator(normalized, profile)
        except Exception as exc:  # noqa: BLE001
            return _failed_output(
                subtask_id=subtask_id,
                request=request,
                reason_code="subtask_result_validator_failed",
                message=str(exc),
                profile=profile,
            )
    return normalized


def _coerce_hydration_result(raw: Any) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    if hasattr(raw, "outputs"):
        outputs = getattr(raw, "outputs", {}) or {}
        evidence = getattr(raw, "image_evidence", ()) or ()
        return dict(outputs) if isinstance(outputs, Mapping) else {}, tuple(
            row for row in evidence if isinstance(row, dict)
        )
    if isinstance(raw, Mapping):
        outputs = raw.get("outputs") if isinstance(raw.get("outputs"), Mapping) else {}
        evidence_raw = raw.get("image_evidence")
        evidence = tuple(row for row in evidence_raw if isinstance(row, dict)) if isinstance(evidence_raw, list) else ()
        return dict(outputs), evidence
    return {}, ()


def _parse_raw_child_output(raw: Any) -> Mapping[str, Any] | None:
    if isinstance(raw, Mapping):
        for key in ("text", "content", "output_text"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    parsed = json.loads(value)
                except Exception:
                    return None
                return parsed if isinstance(parsed, Mapping) else None
        if "status" in raw or "result" in raw:
            return raw
        return None
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except Exception:
            return None
        return parsed if isinstance(parsed, Mapping) else None
    return None


def _failed_output(
    *,
    subtask_id: str,
    request: DelegateSubtaskRequest,
    reason_code: str,
    message: str,
    prompt_char_count: int | None = None,
    model_name: str | None = None,
    image_attachment_count: int | None = None,
    hydration_errors: tuple[Mapping[str, Any], ...] = (),
    profile: SubtaskProfile | None = None,
) -> dict[str, Any]:
    failed_result = (
        empty_result_for_profile(profile, message=message)
        if profile is not None
        else {
            "reading": None,
            "ambiguity": "",
            "observations": [],
            "limits": [_bound_text(message, _MAX_FIELD_CHARS)],
        }
    )
    out: dict[str, Any] = {
        "action_type": DELEGATE_SUBTASK_ACTION_TYPE,
        "subtask_id": str(subtask_id or DELEGATE_SUBTASK_ACTION_TYPE),
        "profile": request.profile,
        "status": "failed",
        "input_refs": list(request.context_refs),
        "result": failed_result,
        "errors": [{"reason_code": reason_code, "message": _bound_text(message, _MAX_FIELD_CHARS)}],
    }
    if hydration_errors:
        out["errors"] = list(out["errors"]) + [dict(row) for row in hydration_errors]
    trace: dict[str, Any] = {}
    if model_name:
        trace["model"] = model_name
    if prompt_char_count is not None:
        trace["prompt_char_count"] = int(prompt_char_count)
    if image_attachment_count is not None:
        trace["image_attachment_count"] = int(image_attachment_count)
    if trace:
        out["subtask_trace"] = trace
    return out


def _bound_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= int(limit):
        return text
    return text[: int(limit)]
