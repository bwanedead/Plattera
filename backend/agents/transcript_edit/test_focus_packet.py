from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.focus_packet import build_focus_packet


def test_focus_packet_caps_spans_image_results_and_feedback() -> None:
    span_context = [
        {"span_id": f"s{i}", "text": "x" * 1000, "start_char": i * 10, "end_char": i * 10 + 5}
        for i in range(20)
    ]
    image_payload = {
        "summary": {"total_checks": 20},
        "results": [{"check_id": f"c{i}", "status": "match", "observed_text": "y" * 1000} for i in range(20)],
    }
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "section",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="section",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=span_context,
        image_verification_payload=image_payload,
        feedback={
            "decision_key": "section",
            "selected_value": "Section 12",
            "note": "n" * 1000,
            "prompt_id": "hitl_section_1_abc123",
        },
        continuity_log=[],
    )
    assert len(packet["span_context"]) <= 6
    assert all(len(str(row.get("text") or "")) <= 320 for row in packet["span_context"])
    results = packet["image_verification"]["results"]
    assert len(results) <= 8
    assert all(str(row.get("decision_key") or "") == "section" for row in results)
    assert len(str(packet["feedback"]["note"] or "")) <= 240


def test_focus_packet_filters_recent_attempts_to_focus_key() -> None:
    packet = build_focus_packet(
        decision_ledger={"items": [{"key": "range", "closure_requirement": {"mapping_blocking": True}}]},
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[
            {"decision_key": "section", "move": "m1", "outcome": "o1"},
            {"decision_key": "range", "move": "m2", "outcome": "o2"},
            {"decision_key": "range", "move": "m3", "outcome": "o3"},
        ],
    )
    attempts = packet["recent_attempts"]
    assert len(attempts) == 2
    assert all(str(row.get("decision_key") or "") == "range" for row in attempts)
