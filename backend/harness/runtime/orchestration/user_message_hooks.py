"""Mechanical glue between the orchestrator loop and the user-message ledger.

Thin orchestrator-side helpers — they poll the on-disk message store, update
the durable ledger, and emit corresponding trace events.  They do not
interpret message content.

Kept out of ``orchestrator.py`` so the user-message lifecycle (inbound /
consumed / deferred) is reviewable in one place, mirroring
``hitl_ledger_hooks.py`` for the HITL channel.
"""

from __future__ import annotations

from typing import Any

from ..memory import LoopMemoryState
from ..user_messages.ledger import (
    mark_consumed as ledger_mark_consumed,
    mark_deferred as ledger_mark_deferred,
)
from ..user_messages.transport import poll_user_messages
from .trace_collector import KernelTraceCollector


def poll_and_record_user_messages(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector,
    iteration: int,
    loop_kind: str,
    run_id: str,
) -> None:
    """Read the user-message store, ingest new entries into the ledger, and
    emit ``user_message_inbound`` trace events for each newly-recorded message.
    """
    def _on_inbound(message_id: str, ledger_entry: dict[str, Any]) -> None:
        tracer.emit_user_message_inbound(
            iteration=iteration,
            message_id=message_id,
            message_payload=ledger_entry,
        )

    loop_memory.continuity.user_message_ledger = poll_user_messages(
        existing_ledger=loop_memory.continuity.user_message_ledger,
        loop_kind=loop_kind,
        run_id=run_id,
        iteration=iteration,
        on_inbound=_on_inbound,
    )


def record_consumed_and_deferred_user_messages(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector,
    iteration: int,
    consumed_ids: tuple[str, ...],
    defers: tuple[dict[str, Any], ...],
) -> None:
    """Apply agent-declared consumes and defers to the ledger and emit a single
    ``user_message_consumed`` trace event summarizing the acknowledgment.

    Increments ``user_message_consumed_unknown_count`` for each declared id
    that does not match any ledger row (drift signal).
    """
    if not consumed_ids and not defers:
        return

    matched_consumed: list[str] = []
    unknown_consumed: list[str] = []
    if consumed_ids:
        ledger, matched_consumed, unknown_consumed = ledger_mark_consumed(
            loop_memory.continuity.user_message_ledger,
            message_ids=consumed_ids,
            iteration=iteration,
        )
        loop_memory.continuity.user_message_ledger = ledger
        if unknown_consumed:
            loop_memory.continuity.user_message_consumed_unknown_count += len(unknown_consumed)

    matched_deferred: list[dict[str, Any]] = []
    unknown_deferred: list[str] = []
    if defers:
        ledger, matched_ids, unknown_ids = ledger_mark_deferred(
            loop_memory.continuity.user_message_ledger,
            defers=list(defers),
            iteration=iteration,
        )
        loop_memory.continuity.user_message_ledger = ledger
        unknown_deferred = list(unknown_ids)
        # Pair each matched id with the reason from the input list for the trace event.
        reasons_by_id = {
            str(d.get("message_id") or ""): str(d.get("reason") or "")
            for d in defers
            if isinstance(d, dict)
        }
        for mid in matched_ids:
            matched_deferred.append({"message_id": mid, "reason": reasons_by_id.get(mid, "")})
        if unknown_deferred:
            loop_memory.continuity.user_message_consumed_unknown_count += len(unknown_deferred)

    tracer.emit_user_message_consumed(
        iteration=iteration,
        consumed_message_ids=matched_consumed,
        unknown_message_ids=list(unknown_consumed) + unknown_deferred,
        deferred=matched_deferred,
    )
