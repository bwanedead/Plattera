"""Transcript-edit run feed + run-centric diagnostic snapshots (Phase 20).

``run_id`` in :meth:`TranscriptEditRunFeedPersistenceService.write_run_snapshot` is the **logical /
durable run identity** (stable across HITL resume for the same API run). Kernel ``session_id`` is an
implementation detail for that run — do not store it in ``run_id`` or resume will look like a new run
in the recent-runs list.

Idempotency for kernel steps remains scoped to the persisted :class:`agent_kernel.run_artifact.RunArtifact`
(one artifact per kernel session / internal run id), not across independent logical runs.
"""
from __future__ import annotations

import json
import os
import tempfile
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config.paths import dossiers_state_root

_LATEST_RUN_FILENAME = "latest_transcript_edit_run.json"
_RECENT_RUNS_FILENAME = "transcript_edit_recent_runs.json"
_RECENT_RUN_LOCK_FILENAME = "transcript_edit_recent_runs.lock"
_DIAGNOSTICS_SUBDIR = "diagnostics"
_RUN_DIAGNOSTIC_SCHEMA_VERSION = "run_diagnostic.v1"
_RECENT_RUN_LIMIT = 5
_RECENT_RUN_LOCK_TIMEOUT_SECONDS = 10.0
_RECENT_RUN_LOCK_STALE_SECONDS = 60.0
_LOG = logging.getLogger(__name__)


class TranscriptEditRunFeedPersistenceService:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else dossiers_state_root() / "transcript_edit" / "run_feed"
        self._root.mkdir(parents=True, exist_ok=True)
        self._diagnostics_root = self._root / _DIAGNOSTICS_SUBDIR
        self._latest_path = self._root / _LATEST_RUN_FILENAME
        self._recent_path = self._root / _RECENT_RUNS_FILENAME
        self._recent_lock_path = self._root / _RECENT_RUN_LOCK_FILENAME

    def _atomic_write(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(prefix="tx_run_feed_", suffix=".json", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
                json.dump(payload, file_obj, ensure_ascii=False, indent=2)
                file_obj.flush()
                os.fsync(file_obj.fileno())
            os.replace(tmp_path, str(path))
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _read_json(self, path: Path) -> dict[str, Any] | None:
        try:
            if not path.exists():
                return None
            with open(path, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")

    @staticmethod
    def _safe_diagnostic_filename(logical_run_id: str) -> str:
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(logical_run_id).strip())[:200]
        return (safe or "run").strip("_") + ".json"

    def _write_run_diagnostic_snapshot(
        self,
        *,
        logical_run_id: str,
        request_id: str,
        session_id: str | None,
        dossier_id: str | None,
        final_status: str,
        reason_code: str | None,
        iterations: int,
        terminal_message: str,
        terminal_summary: dict[str, Any] | None,
        run_artifact_ref: str | None,
        trace_artifact_ref: str | None,
        progress_log: list[dict[str, Any]] | None,
        critical_events: list[dict[str, Any]] | None,
        saved_at_iso: str,
    ) -> str | None:
        """One JSON file per logical run for inspection (progress tail + terminal recap)."""
        try:
            self._diagnostics_root.mkdir(parents=True, exist_ok=True)
            path = self._diagnostics_root / self._safe_diagnostic_filename(logical_run_id)
            payload: dict[str, Any] = {
                "schema_version": _RUN_DIAGNOSTIC_SCHEMA_VERSION,
                "logical_run_id": logical_run_id,
                "request_correlation_id": request_id,
                "kernel_session_id": session_id,
                "dossier_id": dossier_id,
                "final_status": final_status,
                "reason_code": reason_code,
                "iterations": int(iterations),
                "ended_at": saved_at_iso,
                "terminal_message": terminal_message,
                "terminal_summary": self._compact_terminal_summary(terminal_summary),
                "run_artifact_ref": run_artifact_ref,
                "trace_artifact_ref": trace_artifact_ref,
                "progress_log": list(progress_log or [])[-48:],
                "critical_events": list(critical_events or [])[-80:],
            }
            self._atomic_write(path, payload)
            return str(path)
        except Exception:
            return None

    @contextmanager
    def _recent_feed_write_lock(self) -> Iterator[bool]:
        deadline = time.monotonic() + _RECENT_RUN_LOCK_TIMEOUT_SECONDS
        lock_fd: int | None = None
        while True:
            try:
                lock_fd = os.open(str(self._recent_lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                break
            except FileExistsError:
                if self._recent_lock_path.exists():
                    try:
                        age_seconds = time.time() - self._recent_lock_path.stat().st_mtime
                    except Exception:
                        age_seconds = 0.0
                    if age_seconds >= _RECENT_RUN_LOCK_STALE_SECONDS:
                        try:
                            self._recent_lock_path.unlink()
                        except Exception:
                            pass
                        continue
                if time.monotonic() >= deadline:
                    _LOG.warning(
                        "TX_RUN_FEED_LOCK_TIMEOUT ► recent_feed_lock_path=%s",
                        str(self._recent_lock_path),
                    )
                    yield False
                    return
                time.sleep(0.05)
        try:
            with os.fdopen(lock_fd, "w", encoding="utf-8") as file_obj:
                file_obj.write(f"pid={os.getpid()}\ncreated_at={self._utc_now_iso()}\n")
                file_obj.flush()
                os.fsync(file_obj.fileno())
            yield True
        finally:
            try:
                if self._recent_lock_path.exists():
                    self._recent_lock_path.unlink()
            except Exception:
                pass

    def _compact_terminal_summary(self, terminal_summary: dict[str, Any] | None) -> dict[str, Any]:
        summary = terminal_summary if isinstance(terminal_summary, dict) else {}
        rationale = summary.get("final_decision_rationale") if isinstance(summary.get("final_decision_rationale"), dict) else {}
        blocking_breakdown = summary.get("blocking_breakdown") if isinstance(summary.get("blocking_breakdown"), dict) else {}
        return {
            "status": summary.get("status"),
            "reason_code": summary.get("reason_code"),
            "terminal_classification": summary.get("terminal_classification"),
            "mapping_ready": bool(summary.get("mapping_ready")),
            "closure_state": summary.get("closure_state"),
            "mechanical_severity_clear": bool(
                summary.get("mechanical_severity_clear", summary.get("validator_clean"))
            ),
            "scoped_success_eligible": bool(summary.get("scoped_success_eligible")),
            "run_healthy_for_scoped_success": bool(summary.get("run_healthy_for_scoped_success")),
            "why_this_decision": summary.get("why_this_decision"),
            "closure_not_reached_reason": summary.get("closure_not_reached_reason"),
            "blocking_items_count": summary.get("blocking_items_count"),
            "handoff_posture": summary.get("handoff_posture"),
            "blocking_breakdown": {
                "dependency_count": blocking_breakdown.get("dependency_count"),
                "ambiguity_count": blocking_breakdown.get("ambiguity_count"),
                "target_scope_count": blocking_breakdown.get("target_scope_count"),
                "outside_target_scope_count": blocking_breakdown.get("outside_target_scope_count"),
                "unknown_scope_count": blocking_breakdown.get("unknown_scope_count"),
                "optional_unresolved_count": blocking_breakdown.get("optional_unresolved_count"),
            },
            "next_action": summary.get("next_action"),
            "freshness_posture_summary": rationale.get("freshness_posture_summary"),
            "board_run_posture_compact": summary.get("board_run_posture_compact"),
        }

    def _project_latest_run_recap(
        self,
        *,
        request_id: str,
        run_id: str,
        session_id: str | None,
        dossier_id: str | None,
        saved_at: str,
        final_status: str,
        reason_code: str | None,
        iterations: int,
        terminal_message: str,
        terminal_summary: dict[str, Any] | None,
        final_freshness_posture: dict[str, Any] | None,
        final_freshness_summary: str | None,
        run_artifact_ref: str | None,
        handoff_packet_ref: str | None,
        handoff_summary: str | None,
    ) -> dict[str, Any]:
        # ``run_id`` = logical durable run key (stable across HITL resume). ``session_id`` = kernel session.
        return {
            "request_id": request_id,
            "run_id": run_id,
            "session_id": session_id,
            "dossier_id": dossier_id,
            "saved_at": saved_at,
            "ended_at": saved_at,
            "status": final_status,
            "reason_code": reason_code,
            "iterations": int(iterations),
            "terminal_message": terminal_message,
            "terminal_summary": self._compact_terminal_summary(terminal_summary),
            "final_freshness_posture": dict(final_freshness_posture) if isinstance(final_freshness_posture, dict) else None,
            "final_freshness_summary": final_freshness_summary,
            "run_artifact_ref": run_artifact_ref,
            "handoff_packet_ref": handoff_packet_ref,
            "handoff_summary": handoff_summary,
        }

    def _project_recent_run_entry(self, latest_run: dict[str, Any]) -> dict[str, Any]:
        return {
            "request_id": latest_run.get("request_id"),
            "run_id": latest_run.get("run_id"),
            "session_id": latest_run.get("session_id"),
            "dossier_id": latest_run.get("dossier_id"),
            "saved_at": latest_run.get("saved_at"),
            "ended_at": latest_run.get("ended_at"),
            "status": latest_run.get("status"),
            "reason_code": latest_run.get("reason_code"),
            "iterations": latest_run.get("iterations"),
            "terminal_message": latest_run.get("terminal_message"),
            "terminal_classification": (
                (latest_run.get("terminal_summary") or {}).get("terminal_classification")
                if isinstance(latest_run.get("terminal_summary"), dict)
                else None
            ),
            "closure_state": (
                (latest_run.get("terminal_summary") or {}).get("closure_state")
                if isinstance(latest_run.get("terminal_summary"), dict)
                else None
            ),
            "final_freshness_summary": latest_run.get("final_freshness_summary"),
            "run_artifact_ref": latest_run.get("run_artifact_ref"),
        }

    def write_run_snapshot(
        self,
        *,
        request_id: str,
        run_id: str,
        session_id: str | None,
        dossier_id: str | None,
        final_status: str,
        reason_code: str | None,
        iterations: int,
        terminal_message: str,
        terminal_summary: dict[str, Any] | None,
        final_freshness_posture: dict[str, Any] | None,
        final_freshness_summary: str | None,
        run_artifact_ref: str | None = None,
        handoff_packet_ref: str | None = None,
        handoff_summary: str | None = None,
        saved_at: str | None = None,
        progress_log: list[dict[str, Any]] | None = None,
        critical_events: list[dict[str, Any]] | None = None,
        trace_artifact_ref: str | None = None,
    ) -> dict[str, Any]:
        """Persist latest + recent feed. **run_id** must be the logical run id (stable across resume).

        Recent list dedupes by **run_id** only so a resumed run (new ``session_id``) updates the same row.
        """
        saved_at_iso = saved_at or self._utc_now_iso()
        latest_run = self._project_latest_run_recap(
            request_id=request_id,
            run_id=run_id,
            session_id=session_id,
            dossier_id=dossier_id,
            saved_at=saved_at_iso,
            final_status=final_status,
            reason_code=reason_code,
            iterations=iterations,
            terminal_message=terminal_message,
            terminal_summary=terminal_summary,
            final_freshness_posture=final_freshness_posture,
            final_freshness_summary=final_freshness_summary,
            run_artifact_ref=run_artifact_ref,
            handoff_packet_ref=handoff_packet_ref,
            handoff_summary=handoff_summary,
        )

        recent_entry = self._project_recent_run_entry(latest_run)
        recent_payload = {
            "updated_at": saved_at_iso,
            "runs": [recent_entry],
        }

        with self._recent_feed_write_lock() as locked:
            if locked:
                existing = self._read_json(self._recent_path) or {}
                prior_runs = [row for row in list(existing.get("runs") or []) if isinstance(row, dict)]
                deduped = [
                    row
                    for row in prior_runs
                    if str(row.get("run_id") or "") != str(run_id)
                ]
                deduped.insert(0, recent_entry)
                recent_payload = {
                    "updated_at": saved_at_iso,
                    "runs": deduped[:_RECENT_RUN_LIMIT],
                }
                self._atomic_write(self._latest_path, latest_run)
                self._atomic_write(self._recent_path, recent_payload)
            else:
                self._atomic_write(self._latest_path, latest_run)
                existing_recent = self._read_json(self._recent_path)
                if isinstance(existing_recent, dict):
                    recent_payload = existing_recent
        diag_path = self._write_run_diagnostic_snapshot(
            logical_run_id=run_id,
            request_id=request_id,
            session_id=session_id,
            dossier_id=dossier_id,
            final_status=final_status,
            reason_code=reason_code,
            iterations=iterations,
            terminal_message=terminal_message,
            terminal_summary=terminal_summary,
            run_artifact_ref=run_artifact_ref,
            trace_artifact_ref=trace_artifact_ref,
            progress_log=progress_log,
            critical_events=critical_events,
            saved_at_iso=saved_at_iso,
        )
        out: dict[str, Any] = {
            "latest_path": str(self._latest_path),
            "recent_path": str(self._recent_path),
            "latest_run": latest_run,
            "recent_runs": recent_payload,
        }
        if diag_path:
            out["diagnostic_path"] = diag_path
        return out

    def read_latest_run(self) -> dict[str, Any] | None:
        return self._read_json(self._latest_path)

    def read_recent_runs(self) -> dict[str, Any] | None:
        return self._read_json(self._recent_path)


def write_transcript_edit_run_snapshot(
    *,
    request_id: str,
    run_id: str,
    session_id: str | None,
    dossier_id: str | None,
    final_status: str,
    reason_code: str | None,
    iterations: int,
    terminal_message: str,
    terminal_summary: dict[str, Any] | None,
    final_freshness_posture: dict[str, Any] | None,
    final_freshness_summary: str | None,
    run_artifact_ref: str | None = None,
    handoff_packet_ref: str | None = None,
    handoff_summary: str | None = None,
    saved_at: str | None = None,
    progress_log: list[dict[str, Any]] | None = None,
    critical_events: list[dict[str, Any]] | None = None,
    trace_artifact_ref: str | None = None,
    feed_service: TranscriptEditRunFeedPersistenceService | None = None,
) -> dict[str, Any]:
    service = feed_service if feed_service is not None else _DEFAULT_RUN_FEED_PERSISTENCE
    return service.write_run_snapshot(
        request_id=request_id,
        run_id=run_id,
        session_id=session_id,
        dossier_id=dossier_id,
        final_status=final_status,
        reason_code=reason_code,
        iterations=iterations,
        terminal_message=terminal_message,
        terminal_summary=terminal_summary,
        final_freshness_posture=final_freshness_posture,
        final_freshness_summary=final_freshness_summary,
        run_artifact_ref=run_artifact_ref,
        handoff_packet_ref=handoff_packet_ref,
        handoff_summary=handoff_summary,
        saved_at=saved_at,
        progress_log=progress_log,
        critical_events=critical_events,
        trace_artifact_ref=trace_artifact_ref,
    )


_DEFAULT_RUN_FEED_PERSISTENCE = TranscriptEditRunFeedPersistenceService()


__all__ = [
    "TranscriptEditRunFeedPersistenceService",
    "write_transcript_edit_run_snapshot",
]
