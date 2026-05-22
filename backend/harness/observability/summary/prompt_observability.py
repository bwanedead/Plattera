"""Prompt-event summarization for run-summary inspection."""

from __future__ import annotations

from typing import Any

from .common import _as_dict, _as_int, _as_str, _event_kind
from .models import ClosureReadinessProjection, PromptObservabilitySummary
from .prompt_observability_fields import OPTIONAL_INT_FIELDS, STR_FIELDS, ZERO_INT_FIELDS


def _nonblank_strs(values: Any) -> list[str]:
    return [value for value in values if isinstance(value, str) and value.strip()] if isinstance(values, list) else []


def _prompt_observability_summary_from_payload(payload: dict[str, Any], *, default_surface: str | None = None) -> PromptObservabilitySummary:
    summary = payload.get("prompt_observability_summary")
    if not isinstance(summary, dict):
        return PromptObservabilitySummary(last_prompt_event_surface=_as_str(default_surface))
    readiness = _as_dict(summary.get("closure_readiness_projection"))
    data = {key: (_as_int(summary.get(key)) or 0) for key in ZERO_INT_FIELDS}
    data.update({key: _as_int(summary.get(key)) for key in OPTIONAL_INT_FIELDS})
    data.update({key: _as_str(summary.get(key)) for key in STR_FIELDS})
    data["last_prompt_event_surface"] = _as_str(summary.get("last_prompt_event_surface")) or _as_str(default_surface)
    data["closure_readiness_projection"] = ClosureReadinessProjection(
        complete_run_blockers=_nonblank_strs(readiness.get("complete_run_blockers")),
        publish_blockers=_nonblank_strs(readiness.get("publish_blockers")),
    )
    data["mechanical_flags"] = _nonblank_strs(summary.get("mechanical_flags"))
    raw_exchanges = summary.get("recent_hitl_exchanges")
    data["recent_hitl_exchanges"] = [dict(e) for e in raw_exchanges if isinstance(e, dict)][:16] if isinstance(raw_exchanges, list) else []
    raw_messages = summary.get("recent_user_messages")
    data["recent_user_messages"] = [dict(e) for e in raw_messages if isinstance(e, dict)][:16] if isinstance(raw_messages, list) else []
    return PromptObservabilitySummary(**data)


def _prompt_observability_summary_from_trace_events(events: list[dict[str, Any]]) -> PromptObservabilitySummary:
    prompt_events = [
        event
        for event in events
        if _as_str(event.get("phase")) == "prompt_event"
        or _event_kind(event) == "prompt_event"
        or (isinstance(event.get("payload"), dict) and isinstance(event["payload"].get("prompt_event"), dict))
    ]
    last_payload = _as_dict(prompt_events[-1].get("payload")) if prompt_events else {}
    metadata = _as_dict(_as_dict(last_payload.get("prompt_event")).get("metadata"))
    return PromptObservabilitySummary(
        prompt_event_count=len(prompt_events),
        last_prompt_event_id=_as_str(metadata.get("prompt_event_id")),
        last_prompt_event_surface=_as_str(metadata.get("surface")) or _as_str(last_payload.get("surface")),
    )
