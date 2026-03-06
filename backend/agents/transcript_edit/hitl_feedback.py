from __future__ import annotations

import re
import time
from typing import Any
from uuid import uuid4

from services.agent_viewer import feedback_store

from .decision_ledger import unresolved_mapping_blocking_requirements
from .hitl_override_plans import build_feedback_override_plan as build_feedback_override_plan_for_key
from .hitl_override_plans import supported_decision_keys


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
    unresolved_items = unresolved_mapping_blocking_requirements(decision_ledger)
    if not unresolved_items:
        return None
    target = None
    priority = {
        "range": 0,
        "township": 1,
        "section": 2,
        "tie_distance": 3,
        "tie_bearing": 4,
        "closure_or_pob": 5,
        "DELIMITED": 99,
        "acreage": 100,
    }
    unresolved_states = {"unknown", "candidate_found", "disputed", "accepted_with_risk"}
    for item in unresolved_items:
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
        target_req = target.get("closure_requirement") if isinstance(target.get("closure_requirement"), dict) else {}
        item_req = requirement if isinstance(requirement, dict) else {}
        target_is_contradiction = str(target_req.get("block_reason") or "").strip().lower() == "contradiction"
        item_is_contradiction = str(item_req.get("block_reason") or "").strip().lower() == "contradiction"
        if item_is_contradiction and not target_is_contradiction:
            target = item
            continue
        if item_is_contradiction == target_is_contradiction and state == "disputed":
            target_state = str(target.get("state") or "").strip().lower()
            if target_state != "disputed":
                target = item
                continue
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


def list_feedback_entries(*, run_id: str) -> list[dict[str, Any]]:
    entries = feedback_store.list_entries(loop_kind="transcript_edit", run_id=run_id)
    if not isinstance(entries, list):
        return []
    return [entry for entry in entries if isinstance(entry, dict)]


def feedback_entry_signature(entry: dict[str, Any]) -> str:
    submitted = int(entry.get("submitted_at_epoch_seconds") or 0)
    prompt_id = str(entry.get("prompt_id") or "").strip()
    choice = str(entry.get("choice") or "").strip()
    note = str(entry.get("note") or "").strip()
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    decision_key = str(metadata.get("decision_key") or "").strip().lower()
    return f"{submitted}|{prompt_id}|{decision_key}|{choice}|{note}"


def normalize_feedback_response(
    *,
    feedback_entry: dict[str, Any],
    prompt_id: str | None,
    prompt_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(feedback_entry, dict):
        return None
    metadata = feedback_entry.get("metadata") if isinstance(feedback_entry.get("metadata"), dict) else {}
    prompt_ctx = prompt_context if isinstance(prompt_context, dict) else {}
    choice = str(feedback_entry.get("choice") or "").strip()
    note = str(feedback_entry.get("note") or "").strip()
    decision_key = (
        str(metadata.get("decision_key") or "").strip().lower()
        or str(prompt_ctx.get("decision_key") or "").strip().lower()
        or infer_decision_key_from_prompt_id(str(prompt_id or ""))
    )
    if decision_key not in supported_decision_keys():
        return None
    selected_value = str(metadata.get("resolved_value") or "").strip() or choice or _extract_resolved_value_from_note(note) or note
    if not selected_value:
        return None
    return {
        "decision_key": decision_key,
        "selected_value": selected_value,
        "choice": choice or None,
        "note": note or None,
        "prompt_id": str(prompt_id or "").strip() or None,
        "metadata": metadata,
        "prompt_context": prompt_ctx,
    }


def build_feedback_override_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    normalized_feedback: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(normalized_feedback, dict):
        return None
    decision_key = str(normalized_feedback.get("decision_key") or "").strip().lower()
    selected_value = str(normalized_feedback.get("selected_value") or "").strip()
    note = str(normalized_feedback.get("note") or "").strip() or None
    return build_feedback_override_plan_for_key(
        decision_key=decision_key,
        selected_value=selected_value,
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        note=note,
    )


def infer_decision_key_from_prompt_id(prompt_id: str) -> str:
    value = str(prompt_id or "").strip().lower()
    if not value.startswith("hitl_"):
        return ""
    body = value[len("hitl_") :]
    # format: hitl_<decision_key>_<iteration>_<suffix>
    match = re.match(r"^(township|range|section|tie_distance|tie_bearing|closure_or_pob|acreage)_\d+_[a-z0-9]+$", body)
    if match:
        return str(match.group(1))
    return ""


def _extract_resolved_value_from_note(note: str) -> str:
    if not note:
        return ""
    match = re.search(r"resolved\s+[a-z_]+\s+as:\s*(.+)$", note, re.IGNORECASE)
    if match:
        return str(match.group(1)).strip()
    return ""


# Backward-compat wrappers while callers migrate to generic feedback handling.
def range_number_from_feedback(feedback_entry: dict[str, Any]) -> int | None:
    normalized = normalize_feedback_response(
        feedback_entry=feedback_entry,
        prompt_id=str(feedback_entry.get("prompt_id") or ""),
        prompt_context={"decision_key": "range"},
    )
    if not isinstance(normalized, dict):
        return None
    selected_value = str(normalized.get("selected_value") or "")
    match = re.search(r"\b(\d{1,3})\b", selected_value)
    if not match:
        return None
    try:
        value = int(match.group(1))
    except Exception:
        return None
    if 1 <= value <= 200:
        return value
    return None


def build_range_feedback_plan(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    selected_number: int,
) -> dict[str, Any] | None:
    return build_feedback_override_plan_for_key(
        decision_key="range",
        selected_value=str(selected_number),
        source_transcript_ref=source_transcript_ref,
        source_transcript_hash=source_transcript_hash,
        note=None,
    )
