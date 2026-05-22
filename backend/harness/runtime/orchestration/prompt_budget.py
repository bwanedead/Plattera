"""Mechanical per-turn prompt payload budgeting (counts only, bounded).

Budget reports attach to trace/audit metadata — not the model prompt body.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .prompt_sanitization import doctrine_block_layer

_B64_PATTERN = re.compile(r"b64", re.IGNORECASE)
_MAX_TOP_BUCKETS = 12
_DOMAIN_DOCTRINE_LAYERS = frozenset({"domain_branch", "domain_guidance"})

BUDGET_BUCKET_KEYS: tuple[str, ...] = (
    "instruction_text",
    "generic_doctrine",
    "domain_doctrine",
    "surface_blocks",
    "tool_specs_or_surface_payloads",
    "mission_state",
    "resolution_state",
    "latest_refs",
    "evidence_refs",
    "recent_tool_result_slices",
    "recent_action_sequence_result",
    "hydrate_next",
    "pinned_refs",
    "hitl_and_user_messages",
    "prompt_observability_summary",
    "other_structured_state",
    "other_run_context",
    "total_prompt_chars",
)


def measure_json_chars(value: Any) -> int:
    """Deterministic JSON serialization size for budgeting."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value)
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return len(str(value))


def top_prompt_budget_buckets(
    buckets: Mapping[str, int],
    *,
    limit: int = _MAX_TOP_BUCKETS,
) -> list[dict[str, Any]]:
    """Return buckets sorted by char count descending (excluding total)."""
    rows = [
        {"bucket": key, "chars": int(value)}
        for key, value in buckets.items()
        if key != "total_prompt_chars" and int(value) > 0
    ]
    rows.sort(key=lambda row: (-row["chars"], row["bucket"]))
    return rows[:limit]


def build_prompt_budget_report(
    *,
    instruction_text: str,
    prompt_body: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a bounded count-only budget report for one prompt assembly."""
    buckets: dict[str, int] = {key: 0 for key in BUDGET_BUCKET_KEYS}

    buckets["instruction_text"] = len(instruction_text or "")

    doctrine_blocks = prompt_body.get("doctrine_blocks") or []
    if isinstance(doctrine_blocks, list):
        generic: list[Any] = []
        domain: list[Any] = []
        for block in doctrine_blocks:
            if not isinstance(block, Mapping):
                generic.append(block)
                continue
            layer = doctrine_block_layer(block)
            if layer in _DOMAIN_DOCTRINE_LAYERS:
                domain.append(block)
            else:
                generic.append(block)
        buckets["generic_doctrine"] = measure_json_chars(generic)
        buckets["domain_doctrine"] = measure_json_chars(domain)

    surface_packet = prompt_body.get("surface_packet")
    if isinstance(surface_packet, Mapping):
        blocks = surface_packet.get("blocks")
        payloads = surface_packet.get("surface_payloads")
        tool_ids = surface_packet.get("tool_ids")
        buckets["surface_blocks"] = measure_json_chars(blocks)
        tool_part: dict[str, Any] = {}
        if payloads:
            tool_part["surface_payloads"] = payloads
        if tool_ids is not None:
            tool_part["tool_ids"] = tool_ids
        buckets["tool_specs_or_surface_payloads"] = measure_json_chars(tool_part or None)

    run_context = prompt_body.get("run_context")
    if isinstance(run_context, Mapping):
        _accumulate_run_context_buckets(buckets, run_context)

    structured_state = prompt_body.get("structured_state")
    if isinstance(structured_state, Mapping):
        _accumulate_structured_state_buckets(buckets, structured_state)

    mode_keys = {
        key
        for key in prompt_body.keys()
        if key not in {"prompt_mode", "doctrine_blocks", "surface_packet", "run_context", "structured_state"}
    }
    if mode_keys:
        mode_payload = {key: prompt_body[key] for key in mode_keys}
        buckets["other_structured_state"] += measure_json_chars(mode_payload)

    body_without_instruction = dict(prompt_body)
    buckets["total_prompt_chars"] = buckets["instruction_text"] + measure_json_chars(body_without_instruction)

    report: dict[str, Any] = {
        "buckets": {key: buckets[key] for key in BUDGET_BUCKET_KEYS},
        "top_buckets": top_prompt_budget_buckets(buckets),
    }
    return _ensure_budget_report_bounded(report)


def _accumulate_run_context_buckets(buckets: dict[str, int], run_context: Mapping[str, Any]) -> None:
    projection = run_context.get("projection")
    if isinstance(projection, Mapping):
        buckets["mission_state"] += measure_json_chars(projection.get("mission_state"))
        buckets["resolution_state"] += measure_json_chars(projection.get("resolution_state"))
        buckets["latest_refs"] += measure_json_chars(projection.get("latest_refs"))
        buckets["evidence_refs"] += _measure_evidence_refs_in_projection(projection)

    buckets["latest_refs"] += measure_json_chars(run_context.get("latest_refs"))

    hitl_payload: dict[str, Any] = {}
    for key in ("hitl_state", "pending_hitl_requests", "answered_hitl_responses", "operator_progress_message"):
        if key in run_context:
            hitl_payload[key] = run_context[key]
    buckets["hitl_and_user_messages"] += measure_json_chars(hitl_payload or None)

    other_run: dict[str, Any] = {}
    for key, value in run_context.items():
        if key in {
            "projection",
            "latest_refs",
            "hitl_state",
            "pending_hitl_requests",
            "answered_hitl_responses",
            "operator_progress_message",
        }:
            continue
        other_run[key] = value
    buckets["other_run_context"] += measure_json_chars(other_run or None)


def _accumulate_structured_state_buckets(buckets: dict[str, int], structured_state: Mapping[str, Any]) -> None:
    for key in ("recent_tool_result_slices", "recent_action_sequence_result"):
        if key in structured_state:
            buckets[key] += measure_json_chars(structured_state[key])
            if key == "recent_tool_result_slices":
                buckets["evidence_refs"] += _measure_evidence_refs_in_tool_slices(
                    structured_state.get(key)
                )

    hydrate_keys = ("agent_requested_hydration", "pinned_refs_hydration")
    hydrate_payload = {key: structured_state[key] for key in hydrate_keys if key in structured_state}
    buckets["hydrate_next"] += measure_json_chars(hydrate_payload or None)

    if "pinned_refs" in structured_state:
        buckets["pinned_refs"] += measure_json_chars(structured_state["pinned_refs"])

    if "prompt_observability_summary" in structured_state:
        obs = structured_state["prompt_observability_summary"]
        buckets["prompt_observability_summary"] += measure_json_chars(obs)
        buckets["hitl_and_user_messages"] += _measure_user_message_chars(obs)

    other_structured: dict[str, Any] = {}
    accounted = {
        "recent_tool_result_slices",
        "recent_action_sequence_result",
        "agent_requested_hydration",
        "pinned_refs_hydration",
        "pinned_refs",
        "prompt_observability_summary",
    }
    for key, value in structured_state.items():
        if key not in accounted:
            other_structured[key] = value
    buckets["other_structured_state"] += measure_json_chars(other_structured or None)


def _measure_evidence_refs_in_projection(projection: Mapping[str, Any]) -> int:
    resolution = projection.get("resolution_state")
    if not isinstance(resolution, Mapping):
        return 0
    return _measure_evidence_refs_in_work_graph(resolution)


def _measure_evidence_refs_in_work_graph(resolution: Mapping[str, Any]) -> int:
    total = 0
    items = resolution.get("items") or []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, Mapping):
                total += measure_json_chars(item.get("evidence_refs"))
                units = item.get("covered_units") or []
                if isinstance(units, list):
                    for unit in units:
                        if isinstance(unit, Mapping):
                            total += measure_json_chars(unit.get("evidence_refs"))
    return total


def _measure_evidence_refs_in_tool_slices(slices: Any) -> int:
    if not isinstance(slices, list):
        return 0
    total = 0
    for row in slices:
        if not isinstance(row, Mapping):
            continue
        summary = row.get("evidence_artifact_summary")
        if isinstance(summary, Mapping):
            total += measure_json_chars(summary.get("rendered_evidence_refs"))
    return total


def _measure_user_message_chars(obs_summary: Any) -> int:
    if not isinstance(obs_summary, Mapping):
        return 0
    payload: dict[str, Any] = {}
    if obs_summary.get("recent_user_messages"):
        payload["recent_user_messages"] = obs_summary["recent_user_messages"]
    for key in (
        "user_message_pending_count",
        "user_message_consumed_count",
        "user_message_deferred_count",
    ):
        if obs_summary.get(key):
            payload[key] = obs_summary[key]
    return measure_json_chars(payload or None)


def _ensure_budget_report_bounded(report: dict[str, Any]) -> dict[str, Any]:
    """Reject reports that accidentally embed raw payloads or binary markers."""
    serialized = json.dumps(report, ensure_ascii=False, default=str)
    if _B64_PATTERN.search(serialized):
        raise ValueError("prompt budget report must not contain b64 markers")
    if len(serialized) > 8000:
        compact = {
            "buckets": report.get("buckets"),
            "top_buckets": (report.get("top_buckets") or [])[:_MAX_TOP_BUCKETS],
            "truncated": True,
        }
        return compact
    return report
