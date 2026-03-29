from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import dossiers_artifacts_root


def build_handoff_packet(
    *,
    run_id: str,
    request: Any,
    result: Any,
    terminal_summary: dict[str, Any],
    terminal_message: str,
    progress_log: list[dict[str, Any]],
) -> dict[str, Any]:
    decision_ledger = terminal_summary.get("decision_ledger")
    decision_ledger = decision_ledger if isinstance(decision_ledger, dict) else {}
    ledger_items = decision_ledger.get("items")
    ledger_items = ledger_items if isinstance(ledger_items, list) else []
    unresolved_blockers: list[dict[str, Any]] = []
    disputed_items: list[dict[str, Any]] = []
    accepted_with_risk_items: list[dict[str, Any]] = []
    evidence_index: list[str] = []
    for item in ledger_items:
        if not isinstance(item, dict):
            continue
        shape = _compact_item(item)
        state = str(item.get("state") or "unknown")
        if bool(item.get("blocking")) and state in {"unknown", "candidate_found", "disputed", "accepted_with_risk"}:
            unresolved_blockers.append(shape)
        if state == "disputed":
            disputed_items.append(shape)
        if state == "accepted_with_risk":
            accepted_with_risk_items.append(shape)
        for ref in item.get("evidence_refs") or []:
            ref_value = str(ref or "").strip()
            if ref_value and ref_value not in evidence_index:
                evidence_index.append(ref_value)

    pending_feedback_prompts = _pending_feedback_prompts(progress_log)
    user_overrides_applied = _user_overrides_applied(progress_log)
    mapping_ready = bool(terminal_summary.get("mapping_ready"))
    mechanical_clear = bool(terminal_summary.get("mechanical_severity_clear"))
    if not mechanical_clear and terminal_summary.get("validator_clean") is not None:
        mechanical_clear = bool(terminal_summary.get("validator_clean"))
    readiness_blocker = terminal_summary.get("readiness_blocker")
    if mapping_ready:
        resume_recommendation = "proceed"
    elif mechanical_clear:
        resume_recommendation = "proceed_with_caution"
    else:
        resume_recommendation = "requires_upstream_resolution"

    handoff_summary = _handoff_summary_text(
        mapping_ready=mapping_ready,
        unresolved_blockers=unresolved_blockers,
        disputed_items=disputed_items,
        accepted_with_risk_items=accepted_with_risk_items,
        readiness_blocker=readiness_blocker,
    )
    return {
        "packet_version": "transcript_edit_handoff_v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "transcript_edit_run_id": run_id,
        "source_request_id": _read_str(getattr(request, "trigger", None)),
        "transcript_ref": _resolve_transcript_ref(result),
        "identity": {
            "dossier_id": _read_str(getattr(request, "dossier_id", None)),
            "transcription_id": _read_str(getattr(request, "transcription_id", None)),
            "mode": _read_str(getattr(request, "mode", None)),
        },
        "terminal": {
            "status": _read_str(getattr(result, "status", None)),
            "reason_code": _read_str(getattr(result, "reason_code", None)),
            "mechanical_severity_clear": mechanical_clear,
            "mapping_ready": mapping_ready,
            "promoted": bool(terminal_summary.get("promoted")),
            "readiness_blocker": _read_str(readiness_blocker),
            "terminal_message": terminal_message,
            "terminal_summary": terminal_summary,
        },
        "decision_ledger": decision_ledger,
        "unresolved_blockers": unresolved_blockers,
        "disputed_items": disputed_items,
        "accepted_with_risk_items": accepted_with_risk_items,
        "evidence_index": evidence_index,
        "user_overrides_applied": user_overrides_applied,
        "pending_feedback_prompts": pending_feedback_prompts,
        "mapping_watchlist": _mapping_watchlist(unresolved_blockers, disputed_items),
        "resume_recommendation": resume_recommendation,
        "handoff_summary": handoff_summary,
    }


def persist_handoff_packet(*, run_id: str, dossier_id: str | None, packet: dict[str, Any]) -> str:
    safe_dossier = str(dossier_id or "unknown").strip() or "unknown"
    root = dossiers_artifacts_root() / "transcript_edit_handoffs" / safe_dossier
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{run_id}.json"
    path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _resolve_transcript_ref(result: Any) -> str | None:
    latest_refs = getattr(result, "latest_refs", {})
    if not isinstance(latest_refs, dict):
        return None
    for key in ("tx_edited_transcript_ref", "tx_source_transcript_ref"):
        value = latest_refs.get(key)
        if isinstance(value, dict):
            path = _read_str(value.get("artifact_path"))
            if path:
                return path
        path = _read_str(value)
        if path:
            return path
    return None


def _compact_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": _read_str(item.get("key")),
        "selected_value": item.get("selected_value"),
        "alternatives": list(item.get("alternatives") or []),
        "confidence": item.get("confidence"),
        "blocking": bool(item.get("blocking")),
        "state": _read_str(item.get("state")) or "unknown",
        "evidence_refs": list(item.get("evidence_refs") or []),
    }


def _pending_feedback_prompts(progress_log: list[dict[str, Any]]) -> list[str]:
    needed: list[str] = []
    received: set[str] = set()
    for entry in progress_log:
        if not isinstance(entry, dict):
            continue
        event_type = str(entry.get("event_type") or "")
        prompt_id = _read_str(entry.get("prompt_id"))
        if event_type == "human_feedback_needed" and prompt_id:
            needed.append(prompt_id)
        if event_type == "human_feedback" and prompt_id:
            received.add(prompt_id)
    return [prompt for prompt in needed if prompt not in received]


def _user_overrides_applied(progress_log: list[dict[str, Any]]) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for entry in progress_log:
        if not isinstance(entry, dict):
            continue
        phase = str(entry.get("phase") or "")
        if phase not in {"human_feedback_received", "human_feedback_reused"}:
            continue
        values.append(
            {
                "prompt_id": _read_str(entry.get("prompt_id")),
                "message": _read_str(entry.get("message")),
            }
        )
    return values


def _mapping_watchlist(unresolved_blockers: list[dict[str, Any]], disputed_items: list[dict[str, Any]]) -> list[str]:
    watch_keys: list[str] = []
    for item in [*unresolved_blockers, *disputed_items]:
        key = _read_str(item.get("key"))
        if key and key not in watch_keys:
            watch_keys.append(key)
    return watch_keys


def _handoff_summary_text(
    *,
    mapping_ready: bool,
    unresolved_blockers: list[dict[str, Any]],
    disputed_items: list[dict[str, Any]],
    accepted_with_risk_items: list[dict[str, Any]],
    readiness_blocker: Any,
) -> str:
    if mapping_ready:
        return (
            "Mapping-ready. "
            f"{len(disputed_items)} disputed, {len(accepted_with_risk_items)} accepted-with-risk decision(s)."
        )
    blocker = _read_str(readiness_blocker) or "unresolved_mapping_readiness"
    return (
        "Not mapping-ready. "
        f"{len(unresolved_blockers)} blocking decision(s) remain; blocker={blocker}."
    )


def _read_str(value: Any) -> str | None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed:
            return trimmed
    return None
