"""Transport for user-to-agent messages: read the on-disk store and ingest
new entries into the durable per-run ledger.

Analogous to ``runtime/hitl/transport.hitl_poll_feedback_store`` but for the
user-initiated channel.  The poll is idempotent on ``message_id`` so the same
store entry is not double-recorded across iterations.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .ledger import get_message, record_inbound as ledger_record_inbound
from .store import list_entries

OnInboundCallback = Callable[[str, dict[str, Any]], None]


def poll_user_messages(
    *,
    existing_ledger: list[dict[str, Any]],
    loop_kind: str,
    run_id: str,
    iteration: int,
    on_inbound: OnInboundCallback | None = None,
) -> list[dict[str, Any]]:
    """Read the user-message store and append newly-seen entries to the ledger.

    Idempotent on ``message_id``: entries already present in the ledger are
    skipped silently.  ``on_inbound`` fires exactly once per newly-recorded
    message (used by the orchestrator to emit trace events).

    Returns the new ledger (caller assigns it back onto continuity).
    """
    try:
        entries = list_entries(loop_kind=loop_kind, run_id=run_id)
    except Exception:
        return list(existing_ledger)

    new_ledger = list(existing_ledger)
    known_ids = {str(e.get("message_id") or "").strip() for e in new_ledger if e.get("message_id")}

    for raw in entries:
        if not isinstance(raw, dict):
            continue
        mid = str(raw.get("message_id") or "").strip()
        if not mid or mid in known_ids:
            continue
        text_raw = raw.get("text")
        text = text_raw if isinstance(text_raw, str) else str(text_raw or "")
        created_at = raw.get("created_at_epoch_seconds")
        if not isinstance(created_at, (int, float)) or isinstance(created_at, bool):
            created_at = 0
        source_raw = raw.get("source")
        source = source_raw if isinstance(source_raw, str) and source_raw.strip() else None
        metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
        bounds = raw.get("_bounds") if isinstance(raw.get("_bounds"), dict) else None

        new_ledger, newly_appended = ledger_record_inbound(
            new_ledger,
            message_id=mid,
            text=text,
            created_at_epoch_seconds=created_at,
            iteration=iteration,
            source=source,
            metadata=metadata,
            bounds=bounds,
        )
        if newly_appended:
            known_ids.add(mid)
            if on_inbound is not None:
                try:
                    # Hand the ledger entry (post-normalization) to the observer so
                    # trace/audit see the exact bounded payload that was stored.
                    appended = get_message(new_ledger, mid) or {}
                    on_inbound(mid, dict(appended))
                except Exception:  # pragma: no cover — observer must not break transport
                    pass

    return new_ledger
