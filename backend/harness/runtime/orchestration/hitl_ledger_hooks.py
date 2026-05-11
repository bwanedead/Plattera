"""Mechanical glue between the orchestrator loop and the HITL exchange ledger.

These are thin orchestrator-side helpers — they update the durable ledger and
emit corresponding trace events.  They do not interpret request/response content.

Kept out of ``orchestrator.py`` to preserve that file's hotspot budget and to
make the HITL ledger lifecycle (outbound / inbound / consumed) reviewable in one
place.
"""

from __future__ import annotations

from typing import Any

from ..hitl.exchange_ledger import (
    mark_consumed as ledger_mark_consumed,
    record_inbound as ledger_record_inbound,
    record_outbound as ledger_record_outbound,
)
from ..memory import LoopMemoryState
from .trace_collector import KernelTraceCollector


def record_outbound_hitl(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector,
    iteration: int,
    prompt_id: str,
    request_payload: dict[str, Any],
    blocking: bool,
) -> None:
    """Append outbound HITL request to ledger and emit ``hitl_request_outbound`` trace."""
    loop_memory.continuity.hitl_exchange_ledger = ledger_record_outbound(
        loop_memory.continuity.hitl_exchange_ledger,
        prompt_id=prompt_id,
        request_payload=request_payload,
        iteration=iteration,
        blocking=blocking,
    )
    tracer.emit_hitl_request_outbound(
        iteration=iteration,
        prompt_id=prompt_id,
        blocking=blocking,
        request_payload=request_payload,
    )


def make_inbound_hitl_callback(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector,
    iteration: int,
):
    """Build the ``on_inbound`` callback for ``hitl_poll_feedback_store``.

    The closure updates the ledger and emits ``hitl_response_inbound`` only when
    a poll cycle introduces a previously-unanswered exchange (idempotent).
    """
    def _on_inbound(prompt_id: str, feedback: dict[str, Any]) -> None:
        new_ledger, newly_answered = ledger_record_inbound(
            loop_memory.continuity.hitl_exchange_ledger,
            prompt_id=prompt_id,
            response_payload=feedback,
            iteration=iteration,
        )
        loop_memory.continuity.hitl_exchange_ledger = new_ledger
        if newly_answered:
            tracer.emit_hitl_response_inbound(
                iteration=iteration,
                prompt_id=prompt_id,
                response_payload=feedback,
            )

    return _on_inbound


def record_consumed_hitl(
    *,
    loop_memory: LoopMemoryState,
    tracer: KernelTraceCollector,
    iteration: int,
    consumed_ids: tuple[str, ...],
) -> None:
    """Mark exchanges consumed in the ledger and emit ``hitl_response_consumed`` trace.

    Increments ``hitl_consumed_unknown_prompt_count`` for any declared id that
    has no matching ledger entry (drift signal for observability).
    """
    if not consumed_ids:
        return
    new_ledger, matched_ids, unknown_ids = ledger_mark_consumed(
        loop_memory.continuity.hitl_exchange_ledger,
        prompt_ids=consumed_ids,
        iteration=iteration,
    )
    loop_memory.continuity.hitl_exchange_ledger = new_ledger
    if unknown_ids:
        loop_memory.continuity.hitl_consumed_unknown_prompt_count += len(unknown_ids)
    tracer.emit_hitl_response_consumed(
        iteration=iteration,
        consumed_prompt_ids=matched_ids,
        unknown_prompt_ids=unknown_ids,
    )
