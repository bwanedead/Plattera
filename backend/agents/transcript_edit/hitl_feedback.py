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
    decision_ledger: dict[str, Any],
    iteration: int,
) -> dict[str, Any] | None:
    if not isinstance(decision_ledger, dict):
        return None
    items = decision_ledger.get("items")
    if not isinstance(items, list):
        return None
    target = None
    priority = {
        "township": 0,
        "range": 1,
        "section": 2,
        "tie_distance": 3,
        "tie_bearing": 4,
        "closure_or_pob": 5,
        "DELIMITED": 99,
        "acreage": 100,
    }
    unresolved_states = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
    for item in items:
        if not isinstance(item, dict):
            continue
        state = str(item.get("state") or "").strip().lower()
        if state not in unresolved_states:
            continue
        requirement = item.get("closure_requirement")
        if not isinstance(requirement, dict):
            continue
        mapping_blocking = bool(requirement.get("mapping_blocking", item.get("blocking")))
        if not mapping_blocking:
            continue
        if target is None:
            target = item
            continue
        target_key = str(target.get("key") or "")
        key = str(item.get("key") or "")
        if priority.get(key, 50) < priority.get(target_key, 50):
            target = item
    if not isinstance(target, dict):
        return None
    requirement = target.get("closure_requirement") if isinstance(target.get("closure_requirement"), dict) else {}
    key = str(target.get("key") or "decision").strip().lower()
    options = [str(v).strip() for v in list(requirement.get("resolution_options") or []) if str(v).strip()][:4]
    if not options:
        selected = str(target.get("selected_value") or "").strip()
        if selected:
            options = [selected]
    if not options:
        return None
    line1 = str(requirement.get("required_information") or f"Confirm value for {key}").strip()
    line2 = str(requirement.get("minimal_user_action") or "Select the correct value or provide a note.").strip()
    return {
        "prompt_id": f"hitl_{key}_{iteration}_{uuid4().hex[:8]}",
        "line1": line1,
        "line2": line2,
        "choices": options[:4],
        "default_choice": options[0],
        "context": {
            "decision_key": key,
            "closure_requirement": requirement,
        },
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
