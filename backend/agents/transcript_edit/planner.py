from __future__ import annotations

import json
from typing import Any

from services.llm.openai import OpenAIService
from transcript_edit.contracts import EditPlanV0

from .prompting import (
    build_plan_repair_user_message,
    build_planner_system_message,
    build_planner_user_message,
)


class TranscriptEditPlanPlanner:
    def __init__(self, service: OpenAIService | None = None) -> None:
        self._service = service or OpenAIService()

    def propose_plan(
        self,
        *,
        model: str,
        source_transcript_ref: str,
        source_transcript_hash: str,
        findings_summary: dict[str, Any],
        top_findings: list[dict[str, Any]],
        span_context: list[dict[str, Any]],
        max_attempts: int,
    ) -> tuple[EditPlanV0 | None, str, str]:
        if not self._service.is_available() or getattr(self._service, "client", None) is None:
            return None, "planner_unavailable", ""
        api_model = self._service.models.get(model, {}).get("api_model_name", model)
        client = self._service.client

        system_msg = build_planner_system_message()
        user_msg = build_planner_user_message(
            source_transcript_ref=source_transcript_ref,
            source_transcript_hash=source_transcript_hash,
            findings_summary=findings_summary,
            top_findings=top_findings,
            span_context=span_context,
        )
        raw_content = ""
        last_error = "planner_invalid_response"
        for attempt in range(1, max_attempts + 1):
            params: dict[str, Any] = {
                "model": api_model,
                "messages": [
                    {"role": "developer", "content": system_msg},
                    {"role": "user", "content": user_msg},
                ],
                "response_format": {"type": "json_object"},
            }
            if "gpt-5" in str(api_model):
                params["max_completion_tokens"] = 8000
                params["reasoning_effort"] = "medium"
            else:
                params["max_tokens"] = 4000
                params["temperature"] = 0
            completion = client.chat.completions.create(
                **params,
            )
            message = completion.choices[0].message if completion.choices else None
            content = message.content if message is not None else None
            raw_content = content if isinstance(content, str) else ""
            if not raw_content.strip():
                last_error = "planner_empty_response"
                user_msg = build_plan_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    source_transcript_ref=source_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
                continue
            try:
                parsed = json.loads(raw_content)
                if not isinstance(parsed, dict):
                    last_error = "planner_non_object_json"
                    raise ValueError(last_error)
                parsed.setdefault("source_transcript_ref", source_transcript_ref)
                parsed.setdefault("source_transcript_hash", source_transcript_hash)
                plan = EditPlanV0.model_validate(parsed)
                return plan, "ok", raw_content
            except Exception as exc:
                last_error = f"plan_invalid:{type(exc).__name__}"
                user_msg = build_plan_repair_user_message(
                    error_reason=last_error,
                    raw_content=raw_content,
                    source_transcript_ref=source_transcript_ref,
                    source_transcript_hash=source_transcript_hash,
                )
        return None, last_error, raw_content
