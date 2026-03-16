from __future__ import annotations

import hashlib
import time
from typing import Any

from ..tracing.schema import RawTraceEvent

_SOURCE_KIND = "kernel_live"
_MAX_FOCUS_CANDIDATES = 5
_MAX_RATIONALE_CHARS = 256
_MAX_IDEMPOTENCY_KEY_CHARS = 64


class KernelTraceCollector:
    """Accumulates live trace events emitted by the orchestration kernel (Phase 11 D1).

    The kernel creates one collector per loop run and emits events at each phase
    boundary.  At termination, ``build_raw_events()`` returns the serialized events
    for inclusion in ``KernelLoopResult.trace_events``; the calling runtime layer is
    responsible for building a ``CanonicalTraceRecord`` and persisting the trace (D2).

    No I/O is performed here — the collector is purely in-memory.
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
    # Phase-level emit methods
    # ------------------------------------------------------------------

    def emit_request_start(
        self,
        *,
        dossier_id: str | None,
        max_iterations: int,
        run_artifact_ref: str | None,
    ) -> None:
        """Emitted once at loop start (before Phase 1 orient)."""
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
                    "dossier_id": dossier_id,
                    "max_iterations": max_iterations,
                    "run_artifact_ref": run_artifact_ref,
                },
                source_origin=self._source(local_id="request_start"),
            )
        )

    def emit_iteration_start(self, *, iteration: int, hitl_state: str) -> None:
        """Emitted at the top of each iteration before Phase 2 refresh."""
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

    def emit_focus_selected(
        self,
        *,
        iteration: int,
        focus_key: str | None,
        candidates: list[dict[str, Any]],
        stagnation_streak: int | None = None,
    ) -> None:
        """Emitted at Phase 4 after the kernel selects (or fails to select) a focus."""
        top = [
            {
                "focus_key": str(c.get("focus_key") or ""),
                "state": str(c.get("state") or ""),
                "priority": c.get("priority"),
                "focus_source": str(c.get("focus_source") or "") or None,
            }
            for c in candidates[:_MAX_FOCUS_CANDIDATES]
            if isinstance(c, dict)
        ]
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="iteration",
                phase="focus_selection",
                iteration_index=iteration,
                actor="kernel",
                status="completed" if focus_key is not None else "running",
                reason_code="no_actionable_focus" if focus_key is None else None,
                refs_delta={},
                payload={
                    "focus_key": focus_key,
                    "candidates_top": top,
                    "stagnation_streak": stagnation_streak,
                },
                source_origin=self._source(local_id=f"iter_{iteration}_focus"),
            )
        )

    def emit_move_resolved(
        self,
        *,
        iteration: int,
        move_type: str,
        focus_key: str | None,
        rationale: str | None,
        evidence_kind: str | None = None,
        used_hitl_feedback: bool | None = None,
    ) -> None:
        """Emitted at Phase 5b after domain resolves the move decision."""
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="model_proposal",
                phase="move_resolution",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                refs_delta={},
                payload={
                    "move_type": move_type,
                    "focus_key": focus_key,
                    "rationale": (rationale or "")[:_MAX_RATIONALE_CHARS],
                    "evidence_kind": evidence_kind,
                    "used_hitl_feedback": used_hitl_feedback,
                },
                source_origin=self._source(local_id=f"iter_{iteration}_move"),
            )
        )

    def emit_plan_compiled(
        self,
        *,
        iteration: int,
        action_type: str,
        idempotency_key: str,
    ) -> None:
        """Emitted at Phase 5c after the domain compiles the execution plan."""
        fp = (
            hashlib.sha1(idempotency_key.encode(), usedforsecurity=False).hexdigest()[:8]
            if idempotency_key
            else ""
        )
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="model_proposal",
                phase="plan_compilation",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                refs_delta={},
                payload={
                    "action_type": str(action_type),
                    "idempotency_key_fingerprint": fp,
                    "idempotency_key": idempotency_key[:_MAX_IDEMPOTENCY_KEY_CHARS],
                },
                source_origin=self._source(local_id=f"iter_{iteration}_plan"),
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
        """Emitted at Phase 6 after the kernel dispatches the execution step.

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

    def emit_progress_delta(
        self,
        *,
        iteration: int,
        made_progress: bool,
        reason_code: str,
        no_progress_streak: int,
        evidence_signal_counter: int,
        baseline_blocking_count: int | None = None,
        current_blocking_count: int | None = None,
        signature_changed: bool | None = None,
    ) -> None:
        """Emitted at Phase 7 after the kernel evaluates progress."""
        self._append(
            RawTraceEvent(
                timestamp_epoch_seconds=self._now(),
                event_kind="iteration",
                phase="progress_evaluation",
                iteration_index=iteration,
                actor="kernel",
                status="completed",
                reason_code=reason_code,
                refs_delta={},
                payload={
                    "made_progress": made_progress,
                    "reason_code": reason_code,
                    "no_progress_streak": no_progress_streak,
                    "evidence_signal_counter": evidence_signal_counter,
                    "baseline_blocking_count": baseline_blocking_count,
                    "current_blocking_count": current_blocking_count,
                    "signature_changed": signature_changed,
                },
                source_origin=self._source(local_id=f"iter_{iteration}_progress"),
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
        domain: str,
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
                    "domain": domain,
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

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def build_raw_events(self) -> list[dict[str, Any]]:
        """Return accumulated events as plain dicts (JSON-serializable).

        The calling runtime layer passes these to ``build_kernel_direct_trace()``
        to construct a ``CanonicalTraceRecord`` for persistence (D2).
        """
        return [e.model_dump(mode="json") for e in self._events]
