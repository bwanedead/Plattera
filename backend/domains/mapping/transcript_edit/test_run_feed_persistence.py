from __future__ import annotations

import threading
import time
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.services.workflows.mapping.transcription_edit.run_feed_persistence import TranscriptEditRunFeedPersistenceService


def test_run_feed_writes_latest_run_and_recent_feed(tmp_path: Path) -> None:
    service = TranscriptEditRunFeedPersistenceService(root=tmp_path)
    result = service.write_run_snapshot(
        request_id="req-123",
        run_id="logical-run-abc",
        session_id="session-456",
        dossier_id="D1",
        final_status="needs_review",
        reason_code="tx_agent_no_progress:repeat_signal_pressure",
        iterations=4,
        terminal_message="Transcript loop ended needing review.",
        terminal_summary={
            "terminal_classification": "blocked_no_safe_autonomous_move",
            "closure_state": "blocked",
            "status": "needs_review",
            "reason_code": "tx_agent_no_progress:repeat_signal_pressure",
            "why_this_decision": "Run ended without full closure.",
            "handoff_posture": {
                "posture": "blocked_pending_dependency",
                "reason_code": "mapping_critical_dependency_unresolved",
            },
        },
        final_freshness_posture={
            "focus_decision_key": "range",
            "understanding_strength": "moderate",
            "has_fresh_signal": False,
            "cached_context_present": True,
            "repeat_without_signal": True,
        },
        final_freshness_summary="Run ended after repeated no-signal evidence pressure.",
        run_artifact_ref="in-memory://run",
    )
    latest = service.read_latest_run()
    recent = service.read_recent_runs()
    assert Path(result["latest_path"]).exists()
    assert Path(result["recent_path"]).exists()
    assert "diagnostic_path" in result and Path(str(result["diagnostic_path"])).exists()
    assert isinstance(latest, dict)
    assert isinstance(recent, dict)
    assert latest["final_freshness_posture"]["repeat_without_signal"] is True
    assert latest["final_freshness_summary"] == "Run ended after repeated no-signal evidence pressure."
    assert latest["terminal_summary"]["terminal_classification"] == "blocked_no_safe_autonomous_move"
    assert latest["terminal_summary"]["handoff_posture"]["posture"] == "blocked_pending_dependency"
    assert "support_state" not in latest
    assert "investigation_brief" not in latest
    assert "focus_packet" not in latest
    assert isinstance(recent.get("runs"), list)
    assert recent["runs"][0]["request_id"] == "req-123"
    assert recent["runs"][0]["run_id"] == "logical-run-abc"


def test_recent_runs_feed_keeps_newest_five_entries(tmp_path: Path) -> None:
    service = TranscriptEditRunFeedPersistenceService(root=tmp_path)
    for idx in range(6):
        service.write_run_snapshot(
            request_id=f"req-{idx}",
            run_id=f"logical-{idx}",
            session_id=f"session-{idx}",
            dossier_id="D1",
            final_status="completed" if idx % 2 == 0 else "needs_review",
            reason_code=f"reason-{idx}",
            iterations=idx,
            terminal_message=f"message-{idx}",
            terminal_summary={"terminal_classification": f"class-{idx}", "closure_state": "blocked"},
            final_freshness_posture={"has_fresh_signal": idx % 2 == 0, "cached_context_present": True, "repeat_without_signal": idx == 5},
            final_freshness_summary=f"freshness-{idx}",
            run_artifact_ref=f"in-memory://run-{idx}",
            saved_at=f"2026-03-18T20:15:0{idx}.000000Z",
        )
    recent = service.read_recent_runs()
    assert isinstance(recent, dict)
    runs = recent.get("runs")
    assert isinstance(runs, list)
    assert len(runs) == 5
    assert runs[0]["request_id"] == "req-5"
    assert runs[-1]["request_id"] == "req-1"


def test_recent_runs_feed_stays_compact(tmp_path: Path) -> None:
    service = TranscriptEditRunFeedPersistenceService(root=tmp_path)
    service.write_run_snapshot(
        request_id="req-compact",
        run_id="logical-compact",
        session_id="session-compact",
        dossier_id="D1",
        final_status="needs_review",
        reason_code="tx_agent_no_progress:cached_context",
        iterations=2,
        terminal_message="Compact message",
        terminal_summary={
            "terminal_classification": "blocked_cached_context_only",
            "closure_state": "blocked",
            "status": "needs_review",
            "handoff_posture": {
                "posture": "no_handoff",
                "reason_code": "tx_agent_no_handoff",
            },
        },
        final_freshness_posture={
            "focus_decision_key": "range",
            "understanding_strength": "moderate",
            "has_fresh_signal": False,
            "cached_context_present": True,
            "repeat_without_signal": False,
        },
        final_freshness_summary="Run ended with cached context present but no fresh narrowing signal.",
        run_artifact_ref="in-memory://run-compact",
    )
    latest = service.read_latest_run()
    recent = service.read_recent_runs()
    assert isinstance(latest, dict)
    assert isinstance(recent, dict)
    assert "support_state" not in latest
    assert "investigation_brief" not in latest
    assert "focus_packet" not in latest
    assert "progress_log" not in latest
    assert "critical_events" not in latest
    entry = recent["runs"][0]
    assert "support_state" not in entry
    assert "investigation_brief" not in entry
    assert "focus_packet" not in entry

def test_recent_runs_feed_keeps_concurrent_writes(tmp_path: Path) -> None:
    service = TranscriptEditRunFeedPersistenceService(root=tmp_path)
    original_atomic_write = service._atomic_write
    barrier = threading.Barrier(2)

    def _slow_atomic_write(path: Path, payload: dict[str, object]) -> None:
        if path.name == "transcript_edit_recent_runs.json":
            time.sleep(0.05)
        original_atomic_write(path, payload)

    service._atomic_write = _slow_atomic_write  # type: ignore[method-assign]

    def _worker(idx: int) -> None:
        barrier.wait()
        service.write_run_snapshot(
            request_id=f"req-{idx}",
            run_id=f"logical-{idx}",
            session_id=f"session-{idx}",
            dossier_id="D1",
            final_status="completed",
            reason_code=f"reason-{idx}",
            iterations=idx,
            terminal_message=f"message-{idx}",
            terminal_summary={"terminal_classification": f"class-{idx}", "closure_state": "blocked"},
            final_freshness_posture={
                "has_fresh_signal": True,
                "cached_context_present": False,
                "repeat_without_signal": False,
            },
            final_freshness_summary=f"freshness-{idx}",
            run_artifact_ref=f"in-memory://run-{idx}",
        )

    threads = [threading.Thread(target=_worker, args=(idx,), daemon=True) for idx in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
    recent = service.read_recent_runs()
    assert isinstance(recent, dict)
    runs = recent.get("runs")
    assert isinstance(runs, list)
    assert len(runs) == 2
    assert {row["request_id"] for row in runs} == {"req-0", "req-1"}


def test_same_logical_run_id_updates_recent_once_across_session_change(tmp_path: Path) -> None:
    """HITL resume: new kernel session_id but same logical run_id → one recent row, not two."""
    service = TranscriptEditRunFeedPersistenceService(root=tmp_path)
    service.write_run_snapshot(
        request_id="api-run-uuid-1",
        run_id="tx-agent-api-run-uuid-1",
        session_id="kernel-req::run-a",
        dossier_id="D1",
        final_status="waiting_feedback",
        reason_code="blocked",
        iterations=1,
        terminal_message="waiting",
        terminal_summary={"terminal_classification": "blocked_waiting_feedback", "closure_state": "blocked"},
        final_freshness_posture={"has_fresh_signal": False, "cached_context_present": True, "repeat_without_signal": False},
        final_freshness_summary="x",
        run_artifact_ref="mem://1",
    )
    service.write_run_snapshot(
        request_id="api-run-uuid-1",
        run_id="tx-agent-api-run-uuid-1",
        session_id="kernel-req::run-b",
        dossier_id="D1",
        final_status="completed",
        reason_code="done",
        iterations=3,
        terminal_message="done",
        terminal_summary={"terminal_classification": "success", "closure_state": "clear"},
        final_freshness_posture={"has_fresh_signal": True, "cached_context_present": False, "repeat_without_signal": False},
        final_freshness_summary="y",
        run_artifact_ref="mem://2",
    )
    recent = service.read_recent_runs()
    runs = recent.get("runs") if isinstance(recent, dict) else []
    assert isinstance(runs, list)
    assert len(runs) == 1
    assert runs[0]["session_id"] == "kernel-req::run-b"
    assert runs[0]["status"] == "completed"


