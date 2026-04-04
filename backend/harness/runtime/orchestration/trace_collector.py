from __future__ import annotations

import time
from typing import Any

from ...tracing.schema import RawTraceEvent

_SOURCE_KIND = "kernel_live"


class KernelTraceCollector:
    """Accumulates **mechanical** live trace events for one bounded run loop.

    Event kinds and ``phase`` strings describe *what happened in the host* (iteration
    slice, tool execution, terminal, prompt contact metadata)—not a universal
    cognitive staging model (no canonical “focus → move → plan” grammar).

    At termination, ``build_raw_events()`` returns JSON-serializable dicts for
    ``KernelLoopResult.trace_events``; persistence builds a ``CanonicalTraceRecord``
    elsewhere.

    No I/O — in-memory only.
    """

    def __init__(self, *, session_id: str, request_id: str) -> None:
        self._session_id = session_id
        self._request_id = request_id
        self._events: list[RawTraceEvent] = []
        self._seq: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _now(self) -> int:
        return int(time.time())

    def _seq_next(self) -> int:
        s = self._seq
        self._seq += 1
        return s

    def _source(self, *, local_id: str) -> dict[str, Any]:
        return {
            "kind": _SOURCE_KIND,
            "ref": f"session:{self._session_id}",
            "local_id": local_id,
            "sequence_index": self._seq_next(),
        }

    def _append(self, event: RawTraceEvent) -> None:
        self._events.append(event)

    # ------------------------------------------------------------------
    # Emit methods (mechanical loop signals only)
    # ------------------------------------------------------------------

    def emit_request_start(
        self,
        *,
        opaque_run_context: dict[str, Any] | None = None,
        max_iterations: int,
        run_artifact_ref: str | None,
    ) -> None:
        """Emitted once at loop start, before the first iteration."""
        ctx = dict(opaque_run_context) if isinstance(opaque_run_context, dict) else {}
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="request_start",
                phase="bootstrap",
                iteration_index=None,
                actor="kernel",
                status="started",
                refs_delta={},
                payload={
                    "session_id": self._session_id,
                    "request_id": self._request_id,
                    "opaque_run_context": ctx,
                    "max_iterations": max_iterations,
                    "run_artifact_ref": run_artifact_ref,
                },
                source_origin=self._source(local_id="request_start"),
            )
        )

    def emit_iteration_start(self, *, iteration: int, hitl_state: str) -> None:
        """Emitted at the top of each iteration before sync/evaluate/action."""
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="iteration",
                phase="iteration_start",
                iteration_index=iteration,
                actor="kernel",
                status="running",
                refs_delta={},
                payload={"iteration": iteration, "hitl_state": hitl_state},
                source_origin=self._source(local_id=f"iter_{iteration}_start"),
            )
        )

    def emit_state_patch_outcome(
        self,
        *,
        iteration: int,
        outcome: str,
        reason_code: str | None = None,
        gate: str | None = None,
        message: str | None = None,
        execution_reason_code: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        """Mechanical record of state_patch apply / reject / defer (kernel-only; no semantic inference)."""
        _status = "completed" if outcome in ("applied", "no_patch") else "refused"
        payload: dict[str, Any] = {
            "outcome": outcome,
            "gate": gate,
            "message": message,
            "execution_reason_code": execution_reason_code,
        }
        if detail:
            payload["detail"] = dict(detail)
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="state_patch_outcome",
                phase="state_patch",
                iteration_index=iteration,
                actor="kernel",
                status=_status,
                reason_code=reason_code,
                refs_delta={},
                payload=payload,
                source_origin=self._source(local_id=f"iter_{iteration}_state_patch"),
            )
        )

    def emit_execution_result(
        self,
        *,
        iteration: int,
        action_type: str,
        execution_state: str,
        reason_code: str | None,
        retryable: bool | None,
        refs_delta: dict[str, Any] | None,
    ) -> None:
        """After a step dispatch attempt.

        ``execution_state`` is one of: "executed", "refused", "deduped", "skipped".
        """
        _status_map = {
            "executed": "completed",
            "deduped": "completed",
            "refused": "refused",
            "skipped": "completed",
        }
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="tool_execution",
                phase="execution",
                iteration_index=iteration,
                actor="kernel",
                status=_status_map.get(execution_state, "unknown"),
                reason_code=reason_code,
                refs_delta=refs_delta or {},
                payload={
                    "action_type": str(action_type),
                    "execution_state": execution_state,
                    "retryable": retryable,
                },
                source_origin=self._source(local_id=f"iter_{iteration}_exec"),
            )
        )

    def emit_terminal(
        self,
        *,
        iteration: int,
        terminal_class: str,
        reason_code: str,
    ) -> None:
        """Emitted immediately before the kernel loop returns."""
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="terminal_outcome",
                phase="terminal",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                reason_code=reason_code,
                refs_delta={},
                payload={
                    "terminal_class": terminal_class,
                    "reason_code": reason_code,
                },
                source_origin=self._source(local_id=f"iter_{iteration}_terminal"),
            )
        )

    def emit_llm_call_identity(
        self,
        *,
        iteration: int | None,
        surface: str,
        pack_id: str,
        inheritance_mode: str,
        constitution_version: str,
        run_link_id: str,
        model: str,
    ) -> None:
        """Emitted once per LLM call to record prompt identity metadata (D6)."""
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="model_proposal",
                phase="llm_call_identity",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                refs_delta={},
                payload={
                    "surface": surface,
                    "pack_id": pack_id,
                    "inheritance_mode": inheritance_mode,
                    "constitution_version": constitution_version,
                    "run_link_id": run_link_id,
                    "model": model,
                },
                source_origin=self._source(
                    local_id=f"iter_{iteration}_identity_{surface}"
                ),
            )
        )

    def emit_continuity_compacted(
        self,
        *,
        iteration: int,
        prompt_char_count_estimate_before: int,
        journal_entries_compacted_count: int,
        kernel_step_records_compacted_count: int,
        kernel_step_result_records_compacted_count: int = 0,
        verbatim_keep_n: int,
        threshold_chars: int | None = None,
        compaction_prompt_char_count: int | None = None,
        kernel_compaction_covered_through_turn_index_after: int | None = None,
        compaction_trigger_mode: str | None = None,
        estimated_prompt_tokens: int | None = None,
        context_window_tokens: int | None = None,
        used_context_window_fallback: bool | None = None,
        compaction_trigger_fraction: float | None = None,
        estimated_occupancy_fraction: float | None = None,
    ) -> None:
        """Mechanical record of context-window compaction (separate LLM call; not a normal action turn)."""
        payload: dict[str, Any] = {
            "prompt_char_count_estimate_before": int(prompt_char_count_estimate_before),
            "journal_entries_compacted_count": int(journal_entries_compacted_count),
            "kernel_step_records_compacted_count": int(kernel_step_records_compacted_count),
            "kernel_step_result_records_compacted_count": int(kernel_step_result_records_compacted_count),
            "verbatim_keep_n": int(verbatim_keep_n),
        }
        if threshold_chars is not None:
            payload["threshold_chars"] = int(threshold_chars)
        if compaction_prompt_char_count is not None:
            payload["compaction_prompt_char_count"] = int(compaction_prompt_char_count)
        if kernel_compaction_covered_through_turn_index_after is not None:
            payload["kernel_compaction_covered_through_turn_index_after"] = int(
                kernel_compaction_covered_through_turn_index_after
            )
        if compaction_trigger_mode is not None:
            payload["compaction_trigger_mode"] = str(compaction_trigger_mode)
        if estimated_prompt_tokens is not None:
            payload["estimated_prompt_tokens"] = int(estimated_prompt_tokens)
        if context_window_tokens is not None:
            payload["context_window_tokens"] = int(context_window_tokens)
        if used_context_window_fallback is not None:
            payload["used_context_window_fallback"] = bool(used_context_window_fallback)
        if compaction_trigger_fraction is not None:
            payload["compaction_trigger_fraction"] = float(compaction_trigger_fraction)
        if estimated_occupancy_fraction is not None:
            payload["estimated_occupancy_fraction"] = float(estimated_occupancy_fraction)
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="continuity_compacted",
                phase="continuity",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                refs_delta={},
                payload=payload,
                source_origin=self._source(local_id=f"iter_{iteration}_continuity_compacted"),
            )
        )

    def emit_prompt_event(
        self,
        *,
        iteration: int | None,
        prompt_event: dict[str, Any],
        surface: str,
        pack_id: str,
        model: str,
    ) -> None:
        """Emitted once per substantive model call after output is known."""
        prompt_event_id = ""
        metadata = prompt_event.get("metadata") if isinstance(prompt_event.get("metadata"), dict) else {}
        if isinstance(metadata, dict):
            prompt_event_id = str(metadata.get("prompt_event_id") or "").strip()
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="model_proposal",
                phase="prompt_event",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                refs_delta={},
                payload={
                    "prompt_event_id": prompt_event_id or None,
                    "surface": surface,
                    "pack_id": pack_id,
                    "model": model,
                    "prompt_event": prompt_event,
                },
                source_origin=self._source(
                    local_id=f"iter_{iteration}_prompt_event_{surface or 'unknown'}"
                ),
            )
        )

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def build_raw_events(self) -> list[dict[str, Any]]:
        """Return accumulated events as plain dicts (JSON-serializable).

        The calling runtime layer passes these to ``build_kernel_direct_trace()``
        to construct a ``CanonicalTraceRecord`` for persistence (D2).
        """
        return [e.model_dump(mode="json") for e in self._events]
