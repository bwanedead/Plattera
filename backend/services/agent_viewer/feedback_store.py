"""Persistent feedback store for Agent Viewer HITL prompts."""

from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any

from config.paths import dossiers_artifacts_root


def feedback_path(*, loop_kind: str, run_id: str) -> Path:
    return dossiers_artifacts_root() / "agent_viewer" / "feedback" / loop_kind / f"{run_id}.json"


def list_entries(*, loop_kind: str, run_id: str) -> list[dict[str, Any]]:
    path = feedback_path(loop_kind=loop_kind, run_id=run_id)
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    raw = payload.get("entries") if isinstance(payload, dict) else []
    if not isinstance(raw, list):
        return []
    return [entry for entry in raw if isinstance(entry, dict)]


def append_entry(
    *,
    loop_kind: str,
    run_id: str,
    prompt_id: str | None,
    choice: str | None,
    note: str | None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entries = list_entries(loop_kind=loop_kind, run_id=run_id)
    entry = {
        "submitted_at_epoch_seconds": int(time()),
        "prompt_id": prompt_id,
        "choice": choice,
        "note": note,
        "metadata": metadata or {},
    }
    entries.append(entry)
    if len(entries) > 200:
        entries = entries[-200:]
    path = feedback_path(loop_kind=loop_kind, run_id=run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"loop_kind": loop_kind, "run_id": run_id, "entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return entry


def first_matching_prompt_entry(
    *,
    loop_kind: str,
    run_id: str,
    prompt_id: str,
) -> dict[str, Any] | None:
    for entry in list_entries(loop_kind=loop_kind, run_id=run_id):
        if str(entry.get("prompt_id") or "").strip() == str(prompt_id).strip():
            return entry
    return None
