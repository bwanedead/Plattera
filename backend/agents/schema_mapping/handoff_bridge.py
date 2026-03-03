from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config.paths import dossiers_artifacts_root

_MAPPING_ACTIONS = {"compile", "judge", "georeference", "validate", "bundle"}


def load_transcript_handoff_packet(*, handoff_ref: str | None) -> dict[str, Any] | None:
    ref = str(handoff_ref or "").strip()
    if not ref:
        return None
    try:
        path = Path(ref).resolve()
    except Exception:
        return None
    try:
        allowed_root = (dossiers_artifacts_root() / "transcript_edit_handoffs").resolve()
    except Exception:
        return None
    if path != allowed_root and allowed_root not in path.parents:
        return None
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def handoff_bootstrap_metadata(packet: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(packet, dict):
        return {}
    terminal = packet.get("terminal") if isinstance(packet.get("terminal"), dict) else {}
    watchlist = packet.get("mapping_watchlist") if isinstance(packet.get("mapping_watchlist"), list) else []
    metadata = {
        "transcript_handoff_ref": packet.get("transcript_edit_run_id"),
        "transcript_mapping_ready": bool(terminal.get("mapping_ready")),
        "transcript_resume_recommendation": str(packet.get("resume_recommendation") or ""),
        "transcript_handoff_summary": str(packet.get("handoff_summary") or ""),
        "transcript_mapping_watchlist": [str(item) for item in watchlist[:8] if str(item).strip()],
        "transcript_readiness_blocker": str(terminal.get("readiness_blocker") or ""),
    }
    if not bool(terminal.get("mapping_ready")):
        metadata["bootstrap_note"] = "transcript_handoff_not_mapping_ready"
    return metadata


def maybe_build_upstream_correction_request(
    *,
    run_id: str,
    event: dict[str, Any],
    handoff_packet: dict[str, Any] | None,
) -> dict[str, Any] | None:
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    action_type = str(payload.get("action_type") or "").lower()
    if action_type not in _MAPPING_ACTIONS:
        return None
    execution_state = str(payload.get("execution_state") or "").lower()
    refusal = payload.get("refusal") if isinstance(payload.get("refusal"), dict) else {}
    terminal = payload.get("terminal") if isinstance(payload.get("terminal"), dict) else {}
    dash_fc = payload.get("dashboard_failure_classification") if isinstance(payload.get("dashboard_failure_classification"), dict) else {}
    reason_code = str(
        refusal.get("reason_code")
        or terminal.get("reason_code")
        or dash_fc.get("reason_code")
        or ""
    ).strip()
    if execution_state in {"executed", "completed"} and not reason_code:
        return None
    if not _looks_transcript_related(reason_code):
        return None
    decision_keys = _decision_keys_for_reason(reason_code)
    return {
        "request_id": f"map_to_tx_{run_id}_{event.get('timestamp_epoch_seconds') or 0}",
        "source": "mapping",
        "target_mode": "transcript_edit",
        "reason_code": reason_code or "mapping_transcript_suspect",
        "decision_keys": decision_keys,
        "severity": "blocking" if execution_state not in {"executed", "completed"} else "caution",
        "message": (
            f"Mapping stage '{action_type}' signaled transcript-sensitive issue"
            f"{': ' + reason_code if reason_code else ''}."
        ),
        "evidence_refs": _evidence_refs_from_payload(payload),
        "suggested_next_step": "review_transcript_decision_keys",
        "handoff_watchlist": (
            handoff_packet.get("mapping_watchlist")
            if isinstance(handoff_packet, dict) and isinstance(handoff_packet.get("mapping_watchlist"), list)
            else []
        ),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def persist_upstream_correction_requests(
    *,
    run_id: str,
    dossier_id: str | None,
    requests: list[dict[str, Any]],
) -> str | None:
    if not requests:
        return None
    safe_dossier = str(dossier_id or "unknown").strip() or "unknown"
    root = dossiers_artifacts_root() / "mapping_upstream_requests" / safe_dossier
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{run_id}.json"
    payload = {
        "artifact_type": "mapping_upstream_correction_requests_v1",
        "run_id": run_id,
        "dossier_id": safe_dossier,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "requests": requests,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)


def _evidence_refs_from_payload(payload: dict[str, Any]) -> list[str]:
    latest_refs = payload.get("latest_refs") if isinstance(payload.get("latest_refs"), dict) else {}
    refs: list[str] = []
    for value in latest_refs.values():
        if isinstance(value, str) and value.strip():
            refs.append(value.strip())
    return refs[:12]


def _looks_transcript_related(reason_code: str) -> bool:
    lower = reason_code.lower()
    if not lower:
        return False
    tokens = ("bearing", "range", "township", "section", "closure", "distance", "acreage", "plss", "mismatch")
    return any(token in lower for token in tokens)


def _decision_keys_for_reason(reason_code: str) -> list[str]:
    lower = reason_code.lower()
    keys: list[str] = []
    mapping = {
        "range": "range",
        "township": "township",
        "section": "section",
        "bearing": "tie_bearing",
        "distance": "tie_distance",
        "acreage": "acreage",
        "closure": "closure_or_pob",
        "pob": "closure_or_pob",
    }
    for token, key in mapping.items():
        if token in lower and key not in keys:
            keys.append(key)
    return keys
