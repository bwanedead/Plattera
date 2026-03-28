"""Kernel-direct trace adapter — Phase 11 D3.

Builds a ``CanonicalTraceRecord`` from live ``KernelTraceCollector`` events and a
run artifact, without requiring transcript-derived replay input.

This is the canonical trace builder for orchestration-kernel runs. It is the
native path for live kernel-emitted traces.
"""
from __future__ import annotations

import hashlib
from typing import Any

from ..builder import build_canonical_trace
from ..schema import CanonicalTraceRecord, RawTraceEvent, TerminalSnapshot
from .controller_kernel_helpers import (
    as_dict,
    as_int,
    as_str,
    extract_run_id_from_session,
    first_non_empty,
)

_SOURCE_KIND = "kernel_live"


def build_kernel_direct_trace(
    *,
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
    run_artifact_ref: str | None = None,
    trace_id: str | None = None,
) -> CanonicalTraceRecord:
    """Build a ``CanonicalTraceRecord`` from live kernel trace events + run artifact.

    ``trace_events``  — serialised ``RawTraceEvent`` dicts from ``KernelTraceCollector``
    ``run_artifact``  — the session's run artifact dict (used for IDs / timestamps)
    ``run_artifact_ref`` — storage path of the run artifact, for provenance
    ``trace_id``      — optional stable ID; derived from run_id + event count if absent

    Does NOT require a controller transcript (D3).
    """
    run_id = first_non_empty(
        run_artifact.get("run_id"),
        extract_run_id_from_session(as_str(run_artifact.get("session_id"))),
        "unknown_run",
    )
    request_id = first_non_empty(run_artifact.get("request_id"), "unknown_request")
    session_id = first_non_empty(run_artifact.get("session_id"), None)
    started_at = as_int(run_artifact.get("created_at_epoch_seconds")) or _first_event_ts(trace_events) or 0
    canonical_trace_id = trace_id or _default_trace_id(
        run_id=run_id,
        run_artifact_ref=run_artifact_ref,
        event_count=len(trace_events),
    )

    missing_components: list[str] = []
    warnings: list[str] = []
    if not trace_events:
        missing_components.append("kernel_live_trace_events")
        warnings.append("kernel_live_trace_events_empty")

    terminal_snapshot, terminal_reason = _extract_terminal(trace_events, run_artifact)

    return build_canonical_trace(
        trace_id=canonical_trace_id,
        run_id=run_id,
        session_id=session_id,
        request_id=request_id,
        loop_family="controller_kernel",
        request_metadata=_build_request_metadata(run_artifact=run_artifact),
        start_context_summary=_build_start_context_summary(
            run_artifact=run_artifact,
            run_artifact_ref=run_artifact_ref,
        ),
        started_at_epoch_seconds=int(started_at),
        events=trace_events,
        terminal=terminal_snapshot,
        completeness_status="partial" if missing_components else "complete",
        missing_components=missing_components,
        normalization_warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_terminal(
    trace_events: list[dict[str, Any]],
    run_artifact: dict[str, Any],
) -> tuple[TerminalSnapshot, str]:
    """Find the terminal event and build a TerminalSnapshot.

    Falls back to the run_artifact ledger, then synthesises a failed terminal
    when no terminal event is found.
    """
    # Prefer the last ``terminal_outcome`` event in the live events.
    for event in reversed(trace_events):
        if as_str(event.get("event_kind")) != "terminal_outcome":
            continue
        payload = as_dict(event.get("payload")) or {}
        tc = as_str(payload.get("terminal_class")) or "failed"
        rc = as_str(payload.get("reason_code")) or as_str(event.get("reason_code")) or "unknown"
        return TerminalSnapshot(
            terminal_class=tc,
            terminal_reason_code=rc,
            success=(tc == "completed"),
            terminal_metadata={"source": "kernel_live_terminal_event"},
        ), rc

    # Fallback: inspect run_artifact ledger.
    ledger = as_dict(run_artifact.get("idempotency_ledger")) or {}
    for entry in reversed(list(ledger.values())):
        data = as_dict(entry) or {}
        terminal = as_dict(data.get("terminal")) or {}
        if terminal:
            tc = as_str(terminal.get("terminal_outcome")) or "failed"
            rc = as_str(terminal.get("reason_code")) or "run_artifact_terminal"
            return TerminalSnapshot(
                terminal_class=tc,
                terminal_reason_code=rc,
                success=(tc in {"COMPLETED", "completed"}),
                terminal_metadata={"source": "run_artifact_ledger"},
            ), rc

    # Synthesise.
    return TerminalSnapshot(
        terminal_class="failed",
        terminal_reason_code="kernel_terminal_missing",
        success=False,
        terminal_metadata={"source": "synthesised"},
    ), "kernel_terminal_missing"


def _build_request_metadata(*, run_artifact: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "request_id": as_str(run_artifact.get("request_id")),
        "dossier_id": as_str(run_artifact.get("dossier_id")),
        "source_entry_ref": as_str(run_artifact.get("source_entry_ref")),
        # D3: discriminator flag — lets analytics separate native kernel-live traces
        # from other emission paths without touching loop_family.
        # Existing consumers only read known fields; this key is additive.
        "emission_source": "kernel_live",
    }
    return {k: v for k, v in out.items() if v not in (None, "")}


def _build_start_context_summary(
    *,
    run_artifact: dict[str, Any],
    run_artifact_ref: str | None,
) -> dict[str, Any]:
    budget_keys = sorted(as_dict(run_artifact.get("session_budgets") or {}).keys())[:8]
    out: dict[str, Any] = {
        "run_artifact_ref": run_artifact_ref,
        "session_budget_keys": budget_keys,
        "requires_global_placement": run_artifact.get("requires_global_placement"),
        "render_required": run_artifact.get("render_required"),
        "source": "kernel_direct",
    }
    return {k: v for k, v in out.items() if v not in (None, "", [], {})}


def _first_event_ts(trace_events: list[dict[str, Any]]) -> int | None:
    for event in trace_events:
        value = as_int(event.get("timestamp_epoch_seconds"))
        if value is not None:
            return value
    return None


def _default_trace_id(
    *,
    run_id: str,
    run_artifact_ref: str | None,
    event_count: int,
) -> str:
    seed = "|".join([run_id, run_artifact_ref or "", str(event_count), "kernel_direct"])
    digest = hashlib.sha1(seed.encode("utf-8"), usedforsecurity=False).hexdigest()[:10]
    return f"trace:kernel_direct:{run_id}:{digest}"
