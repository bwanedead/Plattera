from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.focus_packet import build_focus_packet
from backend.agents.transcript_edit.blocker_registry import (
    apply_proposed_emergent_blocker_updates,
    initialize_blocker_registry,
)
from backend.agents.transcript_edit.iteration_repair_moves import _append_continuity_step
from backend.agents.transcript_edit.loop_state import TranscriptEditLoopState


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
        visual_evidence_state={
            "mode": "locate",
            "status": "located",
            "query": "q" * 500,
            "selector_type": "normalized_box",
            "source_image_path": "in-memory://source-image.jpg",
            "tx_image_evidence_region_ref": {"artifact_path": "in-memory://region.jpg"},
            "tx_image_evidence_context_ref": {"artifact_path": "in-memory://context.jpg"},
            "locator": {"status": "located", "confidence": "high", "reason": "r" * 500},
            "verify_summary": {"total_checks": 1},
        },
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
    visual = packet.get("visual_evidence") if isinstance(packet.get("visual_evidence"), dict) else {}
    assert str((visual.get("tx_image_evidence_region_ref") or {}).get("artifact_path") or "") == "in-memory://region.jpg"
    assert str(visual.get("selector_type") or "") == "normalized_box"
    assert str(visual.get("source_image_path") or "") == "in-memory://source-image.jpg"
    assert len(str(visual.get("query") or "")) <= 180
    assert len(str(packet["feedback"]["note"] or "")) <= 240


def test_focus_packet_filters_recent_attempts_to_focus_key() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "mapping_blocking": False,
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[
            {"decision_key": "section", "move": "m1", "outcome": "o1"},
            {
                "decision_key": "range",
                "move": "m2",
                "outcome": "o2",
                "state_delta_hint": "move=range; carry_edit_plan",
                "next_open_move_hint": "re_evaluate_resolver_after_evidence_step",
            },
            {"decision_key": "range", "move": "m3", "outcome": "o3"},
        ],
    )
    attempts = packet["recent_attempts"]
    assert len(attempts) == 2
    assert all(str(row.get("decision_key") or "") == "range" for row in attempts)
    assert all("next_open_move_hint" not in row for row in attempts)
    support_state = packet.get("support_state")
    assert isinstance(support_state, dict)
    item_history = support_state.get("item_history")
    assert isinstance(item_history, list)
    assert all("next_open_move_hint" not in row for row in item_history if isinstance(row, dict))
    assert packet.get("investigation_brief") is None
    brief = support_state.get("item_context")
    assert isinstance(brief, dict)
    assert str(brief.get("role") or "") == "sticky_note"
    assert str(brief.get("purpose") or "") == "current_case_understanding"
    assert "next_recommended_action" not in brief
    continuity = support_state.get("continuity_context")
    assert isinstance(continuity, dict)
    assert str(continuity.get("active_item_id") or "") == "range"
    assert str(continuity.get("purpose") or "") == "active_item_continuity"
    evidence = support_state.get("evidence_context")
    assert isinstance(evidence, dict)
    assert str(evidence.get("role") or "") == "evidence_context"
    focus_selection = packet.get("focus_selection")
    if isinstance(focus_selection, dict):
        assert "why_active_now" not in focus_selection
    posture = support_state.get("blocker_posture") if isinstance(support_state.get("blocker_posture"), dict) else {}
    assert str(posture.get("understanding_strength") or "") in {"weak", "moderate", "narrow"}
    assert "needs_orientation" in posture
    assert "needs_inventory" in posture


def test_continuity_step_logging_omits_next_move_hint() -> None:
    state = TranscriptEditLoopState(continuity_log=[])
    _append_continuity_step(
        state,
        focus_key="range",
        move="gather_more_evidence",
        resolver_reason="evidence still open",
        iterations=7,
        focus_source="test",
        state_before_summary={"understanding_strength": "moderate"},
        evidence_kind="image_evidence:select_region",
        state_delta_hint="move=gather_more_evidence; carry_evidence_request",
    )
    assert len(state.continuity_log) == 1
    row = state.continuity_log[0]
    assert str(row.get("decision_key") or "") == "range"
    assert str(row.get("move") or "") == "gather_more_evidence"
    assert str(row.get("state_delta_hint") or "").startswith("move=gather_more_evidence")
    assert "next_open_move_hint" not in row


def test_focus_packet_materiality_comes_from_closure_requirement() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "mapping_blocking": False,
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    posture = (packet.get("support_state") or {}).get("blocker_posture") if isinstance(packet.get("support_state"), dict) else {}
    assert isinstance(posture, dict)
    assert posture.get("needs_inventory") is True
    assert posture.get("needs_orientation") is True


def test_focus_packet_flags_repeated_no_signal_evidence_attempts() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[{"span_id": "cached", "text": "cached span"}],
        image_verification_payload={
            "results": [{"check_id": "cached_check", "status": "match", "observed_text": "cached image"}]
        },
        visual_evidence_state={
            "status": "located",
            "query": "cached query",
            "tx_image_evidence_region_ref": {"artifact_path": "in-memory://region.jpg"},
        },
        feedback=None,
        continuity_log=[
            {"decision_key": "range", "move": "gather_more_evidence", "outcome": "ok", "evidence_kind": "image_evidence:select_region"},
            {"decision_key": "range", "move": "gather_more_evidence", "outcome": "ok", "evidence_kind": "image_evidence:select_region"},
        ],
        evidence_repeat_guard={"range|repeat": {"count": 2, "last_signal_counter": 2}},
        evidence_signal_counter=2,
    )
    posture = (packet.get("support_state") or {}).get("blocker_posture") if isinstance(packet.get("support_state"), dict) else {}
    assert isinstance(posture, dict)
    assert posture.get("cached_context_present") is True
    assert posture.get("has_new_signal") is False
    assert posture.get("repeat_without_signal") is True


def test_focus_packet_marks_fresh_signal_when_iteration_produces_new_context() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[{"span_id": "fresh", "text": "fresh span"}],
        image_verification_payload={
            "results": [{"check_id": "fresh_check", "status": "match", "observed_text": "fresh image"}]
        },
        visual_evidence_state={
            "status": "verified",
            "query": "fresh query",
            "tx_image_evidence_region_ref": {"artifact_path": "in-memory://fresh-region.jpg"},
        },
        feedback={"decision_key": "range", "selected_value": "Range 75 West"},
        continuity_log=[],
        evidence_repeat_guard={"range|repeat": {"count": 0, "last_signal_counter": 0}},
        evidence_signal_counter=1,
    )
    posture = (packet.get("support_state") or {}).get("blocker_posture") if isinstance(packet.get("support_state"), dict) else {}
    assert isinstance(posture, dict)
    assert posture.get("has_new_signal") is True
    assert posture.get("has_fresh_signal") is True
    assert posture.get("cached_context_present") is True
    assert posture.get("repeat_without_signal") is False


def test_focus_packet_injects_answered_unintegrated_human_resolution_ticket() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [{"key": "range", "state": "disputed", "blocking": True, "closure_requirement": {"mapping_blocking": True}}],
            "external_context_injections": [
                {
                    "type": "human_resolution_ticket",
                    "ticket_id": "hitl_range_1_x",
                    "decision_key": "range",
                    "lifecycle_state": "answered_unintegrated",
                    "strength": "binding",
                    "created_at": 1,
                    "updated_at": 2,
                    "payload": {
                        "issue_summary": "Range contradiction",
                        "normalized_answer_summary": "Range 75 West",
                        "selected_choice": "Range 75 West",
                    },
                }
            ],
        },
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    injections = packet.get("external_context_injections")
    assert isinstance(injections, list) and len(injections) == 1
    row = injections[0]
    assert str(row.get("type") or "") == "human_resolution_ticket"
    assert str(row.get("lifecycle_state") or "") == "answered_unintegrated"
    assert str((row.get("payload") or {}).get("normalized_answer_summary") or "") == "Range 75 West"
    blocker_state = packet.get("blocker_feedback_state")
    assert isinstance(blocker_state, dict)
    focused_pair = packet.get("focused_blocker_feedback_pair")
    assert isinstance(focused_pair, dict)
    assert str(focused_pair.get("decision_key") or "") == "range"
    assert str(focused_pair.get("pair_state") or "") in {
        "feedback_ready_for_integration",
        "answered_unintegrated",
    }
    support_state = packet.get("support_state")
    assert isinstance(support_state, dict)
    brief = support_state.get("item_context")
    assert isinstance(brief, dict)
    assert isinstance(brief.get("knowns"), dict)
    assert isinstance(brief.get("open_questions"), list)
    assert str((support_state.get("continuity_context") or {}).get("role") or "") == "continuity_context"
    assert isinstance((support_state.get("blocker_posture") or {}), dict)


def test_focus_packet_preserves_unknown_scope_as_none_for_in_target_flag() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "in_target_scope": None,
                    "closure_requirement": {
                        "mapping_blocking": True,
                        "scope_status": "unknown",
                        "scope_proof": [],
                    },
                }
            ]
        },
        decision_key="range",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    assert packet["scope_context"]["in_target_scope"] is None


def test_focus_packet_includes_convention_and_emergent_blocker_views() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        blocker_registry={
            "active_blocker_id": "blocker:range",
            "counts": {"open": 1, "waiting_feedback": 0, "answered_unintegrated": 0, "resolved": 0, "superseded": 0, "total": 1},
            "convention_context": {"document_convention": "plss", "convention_confidence": 0.9},
            "archetype_menu": {"menu_family_candidates": ["plss"], "archetypes": [{"archetype_id": "conflicting_location_token"}]},
            "emergent": {
                "active_blocker_id": "emergent:blocker:range",
                "counts": {"open": 1, "total": 1},
                "rows": [{"blocker_id": "emergent:blocker:range", "legacy_decision_key": "range"}],
            },
            "rows": [{"blocker_id": "blocker:range", "decision_key": "range", "state": "open"}],
        },
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    blocker_registry = packet.get("blocker_registry")
    assert isinstance(blocker_registry, dict)
    convention = blocker_registry.get("convention_context")
    assert isinstance(convention, dict)
    assert str(convention.get("document_convention") or "") == "plss"
    emergent = blocker_registry.get("emergent")
    assert isinstance(emergent, dict)
    rows = emergent.get("rows")
    assert isinstance(rows, list) and len(rows) == 1


def test_focus_packet_reflects_runtime_applied_emergent_update() -> None:
    registry = initialize_blocker_registry(
        run_id="run-focus-emergent",
        session_id="session-focus-emergent",
        source_transcript_ref="in-memory://source.json",
    )
    apply_result = apply_proposed_emergent_blocker_updates(
        registry=registry,
        blocker_updates=[
            {
                "operation": "add",
                "blocker_kind": "custom:unknown_notation",
                "title": "Unknown Notation",
                "blocking_class": "mapping_blocking",
                "reason": "Unrecognized shorthand in callout.",
                "scope_status": "unknown",
            }
        ],
        fallback_decision_key="range",
    )
    updated = apply_result["registry"]
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        blocker_registry=updated,
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    emergent = (
        (packet.get("blocker_registry") or {}).get("emergent")
        if isinstance(packet.get("blocker_registry"), dict)
        else {}
    )
    rows = [row for row in list((emergent or {}).get("rows") or []) if isinstance(row, dict)]
    assert any(str(row.get("title") or "") == "Unknown Notation" for row in rows)


def test_focus_packet_marks_emergent_focus_source_and_blocker_fields() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "range",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True},
                }
            ]
        },
        decision_key="range",
        focus_source="emergent_blocker",
        active_emergent_blocker={
            "blocker_id": "emergent:agent:test:1",
            "blocker_kind": "custom:scan_smudge",
            "title": "Smudge On Range",
            "blocking_class": "mapping_blocking",
            "reason": "Digit is smudged",
            "resolution_condition": "Need clearer image",
            "candidate_values": ["74", "75"],
            "next_valid_actions": ["gather_image_evidence", "request_hitl"],
            "scope_status": "in_target",
        },
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    assert str(packet.get("focus_source") or "") == "emergent_blocker"
    assert packet.get("recent_iteration_lane") is None
    blocker = packet.get("active_emergent_blocker")
    assert isinstance(blocker, dict)
    assert str(blocker.get("blocker_id") or "") == "emergent:agent:test:1"
    assert str(blocker.get("blocking_class") or "") == "mapping_blocking"


def test_focus_packet_execution_context_parity_and_generic_knowns() -> None:
    packet = build_focus_packet(
        decision_ledger={
            "items": [
                {
                    "key": "township",
                    "label": "Township",
                    "state": "disputed",
                    "blocking": True,
                    "closure_requirement": {"mapping_blocking": True, "scope_status": "in_target"},
                    "evidence_refs": ["f1"],
                }
            ],
            "source_completeness": "unknown",
        },
        decision_key="township",
        focus_source="legacy_fallback",
        loop_iteration=3,
        active_emergent_blocker=None,
        blocker_registry=None,
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:t",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[
            {
                "decision_key": "township",
                "move": "gather_more_evidence",
                "outcome": "ok",
                "iteration": 2,
                "state_delta_hint": "gather_more_evidence; status=ok",
            }
        ],
    )
    ec = packet.get("execution_context")
    assert isinstance(ec, dict)
    assert isinstance(ec.get("organized_work_note"), str) and ec.get("organized_work_note")
    parity = ec.get("parity")
    assert isinstance(parity, dict)
    assert parity.get("code") == "ok"
    assert parity.get("identity_aligned") is True
    support_state = packet.get("support_state")
    assert isinstance(support_state, dict)
    brief = support_state.get("investigation_brief")
    assert isinstance(brief, dict)
    gwb = (brief.get("knowns") or {}).get("generic_work_board")
    assert isinstance(gwb, dict)
    assert gwb.get("item_id") == "te:ledger:township"
    rich = (ec.get("recent_iterations") or {}).get("rich_capsules") or []
    assert rich
    assert packet.get("recent_iteration_lane") is None
    step0 = rich[0]["steps"][0]
    assert "gather_more_evidence" in (step0.get("state_changes_hint") or "")


def test_focus_packet_malformed_ledger_items_graceful_parity() -> None:
    packet = build_focus_packet(
        decision_ledger={"items": "not-a-list", "source_completeness": "unknown"},
        decision_key="range",
        active_emergent_blocker=None,
        blocker_registry=None,
        source_transcript_ref="ref",
        source_transcript_hash="h",
        span_context=[],
        image_verification_payload={},
        feedback=None,
        continuity_log=[],
    )
    ec = packet.get("execution_context")
    assert (ec.get("parity") or {}).get("code") == "ledger_item_missing"
    assert ec.get("active_work_item") is None
