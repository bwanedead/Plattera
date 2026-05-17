"""Persistent on-disk store for user-to-agent messages.

Mirrors ``services.agent_viewer.feedback_store`` layout/conventions so the
operator CLI, UI, and API can all share one append-only file per run.

The store is the *delivery channel*; the durable per-run ledger lives in
``OrchestrationContinuity.user_message_ledger``.  ``poll_user_messages`` reads
new entries from this store on each iteration and ingests them into the
ledger via ``record_user_message_inbound``.
"""

from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any

from config.paths import dossiers_artifacts_root
from services.agent_viewer.identifiers import validate_viewer_identifiers

from .ledger import make_message_id
from .message_shape import normalize_user_message

# Cap to prevent the store from growing unboundedly across long-running tests.
# The per-run ledger has its own cap; this one just keeps the file small.
_STORE_MAX_ENTRIES = 200


def user_messages_path(*, loop_kind: str, run_id: str) -> Path:
    safe_loop_kind, safe_run_id = validate_viewer_identifiers(loop_kind=loop_kind, run_id=run_id)
    return (
        dossiers_artifacts_root()
        / "agent_viewer"
        / "user_messages"
        / safe_loop_kind
        / f"{safe_run_id}.json"
    )


def list_entries(*, loop_kind: str, run_id: str) -> list[dict[str, Any]]:
    """Return all stored user-message entries for this run, in insertion order."""
    path = user_messages_path(loop_kind=loop_kind, run_id=run_id)
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
    text: str,
    source: str | None = None,
    message_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append a single user message entry and return the persisted row.

    ``message_id`` is generated when not provided so callers get a deterministic
    handle they can later use to mark consumed/deferred.
    """
    mid = (message_id or "").strip() or make_message_id()
    entries = list_entries(loop_kind=loop_kind, run_id=run_id)
    raw_entry: dict[str, Any] = {
        "message_id": mid,
        "created_at_epoch_seconds": int(time()),
        "source": source,
        "text": text,
        "metadata": metadata or {},
    }
    entry = normalize_user_message(raw_entry)
    entries.append(entry)
    if len(entries) > _STORE_MAX_ENTRIES:
        entries = entries[-_STORE_MAX_ENTRIES:]
    path = user_messages_path(loop_kind=loop_kind, run_id=run_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"loop_kind": loop_kind, "run_id": run_id, "entries": entries},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return entry
