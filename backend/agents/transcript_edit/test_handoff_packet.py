from __future__ import annotations

import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.handoff_packet import build_handoff_packet, persist_handoff_packet


class _Request:
    dossier_id = "D1"
    transcription_id = "T1"
    mode = "audit_then_repair_then_promote"
    trigger = "manual"


class _Result:
    status = "needs_review"
    reason_code = "tx_agent_final_image_verify_failed:mismatch"
    latest_refs = {
        "tx_edited_transcript_ref": {"artifact_path": "in-memory://edited.json"},
    }


def test_build_handoff_packet_includes_terminal_and_ledger_views() -> None:
    packet = build_handoff_packet(
        run_id="tx_agent_test",
        request=_Request(),
        result=_Result(),
        terminal_summary={
            "mechanical_severity_clear": True,
            "mapping_ready": False,
            "promoted": False,
            "readiness_blocker": "mapping_critical_image_verification_unresolved",
            "decision_ledger": {
                "items": [
                    {
                        "key": "range",
                        "state": "disputed",
                        "selected_value": "75 west",
                        "alternatives": ["75 west", "74 west"],
                        "blocking": True,
                        "confidence": "medium",
                        "evidence_refs": ["image_check_range_tokens"],
                    }
                ],
                "summary": {"blocking_open_count": 1},
            },
        },
        terminal_message="Not mapping-ready.",
        progress_log=[
            {"event_type": "human_feedback_needed", "prompt_id": "p1"},
            {"event_type": "status"},
        ],
    )
    assert packet["packet_version"] == "transcript_edit_handoff_v1"
    assert packet["terminal"]["mapping_ready"] is False
    assert packet["resume_recommendation"] == "proceed_with_caution"
    assert packet["unresolved_blockers"][0]["key"] == "range"
    assert packet["pending_feedback_prompts"] == ["p1"]
    assert "range" in packet["mapping_watchlist"]


def test_persist_handoff_packet_writes_json_file() -> None:
    packet = {"packet_version": "transcript_edit_handoff_v1"}
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "artifacts"
        import backend.agents.transcript_edit.handoff_packet as hp

        original = hp.dossiers_artifacts_root
        try:
            hp.dossiers_artifacts_root = lambda: root  # type: ignore[assignment]
            ref = persist_handoff_packet(run_id="run-1", dossier_id="D1", packet=packet)
            saved = Path(ref)
            assert saved.exists()
            assert "transcript_edit_handoffs" in str(saved)
        finally:
            hp.dossiers_artifacts_root = original  # type: ignore[assignment]
