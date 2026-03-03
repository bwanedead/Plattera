from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from services.agent_viewer import feedback_store

from .span_seeds import load_transcript_text_for_seeds


def viewer_run_id_from_request_prefix(request_id_prefix: str) -> str:
    value = str(request_id_prefix or "").strip()
    if value.startswith("tx-agent-"):
        return value[len("tx-agent-") :]
    return value


def build_human_feedback_prompt(
    *,
    disagreement_hints: dict[str, Any],
    top_findings: list[dict[str, Any]],
    iteration: int,
) -> dict[str, Any] | None:
    if not isinstance(disagreement_hints, dict):
        return None
    range_values = disagreement_hints.get("range_values")
    if not (isinstance(range_values, list) and len(range_values) > 1):
        return None
    options: list[str] = []
    for item in range_values[:4]:
        if not isinstance(item, dict):
            continue
        token = str(item.get("value") or "").strip().lower()
        m = re.match(r"r(\d{1,3})([we])$", token)
        if not m:
            continue
        num = m.group(1)
        direction = "West" if m.group(2) == "w" else "East"
        options.append(f"Range {num} {direction}")
    options = [opt for opt in options if opt]
    if len(options) < 2:
        return None
    top_message = ""
    for finding in top_findings:
        if not isinstance(finding, dict):
            continue
        msg = str(finding.get("message") or "").strip()
        if msg:
            top_message = msg[:180]
            break
    return {
        "prompt_id": f"hitl_range_{iteration}_{uuid4().hex[:8]}",
        "line1": "Confirm range token for this deed",
        "line2": "Image/text checks disagree on range values; promotion is blocked pending your choice.",
        "choices": options[:4],
        "default_choice": options[0],
        "context": {"top_finding": top_message, "range_values": range_values[:4]},
    }


def wait_for_feedback_response(
    *,
    run_id: str,
    prompt_id: str,
    timeout_seconds: int,
    poll_interval_seconds: int,
) -> dict[str, Any] | None:
    deadline = time.time() + max(1, int(timeout_seconds))
    while time.time() < deadline:
        entry = feedback_store.first_matching_prompt_entry(
            loop_kind="transcript_edit",
            run_id=run_id,
            prompt_id=prompt_id,
        )
        if isinstance(entry, dict):
            return entry
        time.sleep(max(1, int(poll_interval_seconds)))
    return None


def poll_feedback_response(
    *,
    run_id: str,
    prompt_id: str,
) -> dict[str, Any] | None:
    return feedback_store.first_matching_prompt_entry(
        loop_kind="transcript_edit",
        run_id=run_id,
        prompt_id=prompt_id,
    )


def range_number_from_feedback(feedback_entry: dict[str, Any]) -> int | None:
    if not isinstance(feedback_entry, dict):
        return None
    choice = str(feedback_entry.get("choice") or "").strip()
    note = str(feedback_entry.get("note") or "").strip()
    for text in (choice, note):
        m = re.search(r"\b(\d{1,3})\b", text)
        if not m:
            continue
        try:
            num = int(m.group(1))
        except Exception:
            continue
        if 1 <= num <= 200:
            return num
    return None


def build_range_feedback_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    selected_number: int,
) -> dict[str, Any] | None:
    text = load_transcript_text_for_seeds(source_transcript_ref)
    if not text:
        return None
    ops: list[dict[str, Any]] = []
    pattern = re.compile(r"\bRange\b[^()\n]{0,80}\((\d{1,3})\)\s*(West|East)\b", re.IGNORECASE)
    for idx, m in enumerate(pattern.finditer(text)):
        current = m.group(1)
        try:
            current_num = int(current)
        except Exception:
            continue
        if current_num == selected_number:
            continue
        ops.append(
            {
                "op_id": f"hitl-range-{idx+1}",
                "op_type": "replace_span",
                "change_class": "semantic",
                "confidence": "medium",
                "review_required": True,
                "reason": "Human selected range token to resolve blocking conflict.",
                "evidence_refs": [],
                "target": {
                    "locator_type": "offsets",
                    "start_char": int(m.start(1)),
                    "end_char": int(m.end(1)),
                },
                "expected_old": {"old_excerpt": str(current)},
                "new_text": str(selected_number),
            }
        )
        if len(ops) >= 2:
            break
    if not ops:
        return None
    return {
        "plan_version": "edit_plan_v0",
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "plan_id": f"hitl-range-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
        "summary": "Apply human-selected range token to resolve blocking conflict.",
        "ops": ops,
        "global_flags": {
            "review_required": True,
            "rationale": "Human-guided semantic correction.",
        },
    }
