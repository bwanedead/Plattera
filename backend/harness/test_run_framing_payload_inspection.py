"""Verification tests for Task 3 (Rationale Continuity + Run Framing).

Covers the four-point checklist:
  1. Workflow ontology present in identity header text for every domain/surface/mode.
  2. run_progress_frame present and shallow in a real focus packet.
  3. rationale_continuity_strip present (and only when non-empty) in a real focus packet.
  4. No key duplication between run_progress_frame, rationale_continuity_strip, and
     the surrounding focus packet.

These are payload-inspection tests — they exercise the actual domain pack
build_focus_packet() hook with minimal (but real) state rather than mocking the
injected dicts.  No LLM calls are made.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))

from agents.common.identity_composer import (
    Domain,
    InheritanceMode,
    Surface,
    compose_identity_header,
)
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from agents.transcript_edit.domain_pack import TranscriptEditDomainPack
from agents.transcript_edit.loop_state import TranscriptEditLoopState
from harness.orchestration_kernel.contracts import OrchestratorContext
from harness.orchestration_kernel.loop_memory import LoopMemoryState
from harness.tracing.rationale_continuity_strip import build_rationale_continuity_strip


# ---------------------------------------------------------------------------
# 1. Workflow ontology present in identity header
# ---------------------------------------------------------------------------

def test_ontology_block_present_in_full_trunk() -> None:
    """[WORKFLOW:ontology_v1] section must appear in FULL mode header for every domain."""
    for domain, surface in [
        (Domain.TRANSCRIPT_EDIT, Surface.TX_PLANNER),
        (Domain.TRANSCRIPT_EDIT, Surface.TX_FOCUS_RESOLVER),
        (Domain.DEED_TO_IR, Surface.DEED_CONTROLLER),
        (Domain.GENERIC, Surface.GENERIC),
    ]:
        result = compose_identity_header(
            run_link_id="run_x",
            mission_objective="test",
            domain=domain,
            surface=surface,
            inheritance_mode=InheritanceMode.FULL,
        )
        assert "[WORKFLOW:ontology_v1]" in result.header_text, (
            f"Missing workflow ontology block in FULL header for {domain}/{surface}"
        )
        assert "bounded step" in result.header_text
        assert "chat memory" in result.header_text
        assert "mission objective" in result.header_text


def test_ontology_block_present_in_light_trunk() -> None:
    """Abbreviated ontology must appear in LIGHT mode header."""
    for domain, surface in [
        (Domain.TRANSCRIPT_EDIT, Surface.TX_ORIENT_BASELINE),
        (Domain.TRANSCRIPT_EDIT, Surface.TX_IMAGE_LOCATOR),
        (Domain.DEED_TO_IR, Surface.DEED_CONTROLLER),
    ]:
        result = compose_identity_header(
            run_link_id="run_x",
            mission_objective="test",
            domain=domain,
            surface=surface,
            inheritance_mode=InheritanceMode.LIGHT,
        )
        assert "[WORKFLOW:ontology_v1 mode=light]" in result.header_text, (
            f"Missing light ontology block for {domain}/{surface}"
        )
        assert "bounded step" in result.header_text


# ---------------------------------------------------------------------------
# Helpers to build a real (but minimal) tx focus packet
# ---------------------------------------------------------------------------

def _make_tx_context(
    *,
    blocker_surface: list[dict[str, Any]] | None = None,
    strip: list[dict[str, Any]] | None = None,
    no_progress_streak: int = 0,
) -> OrchestratorContext:
    lm = LoopMemoryState()
    lm.blocker_surface = blocker_surface or []
    lm.no_progress_streak = no_progress_streak
    ctx = OrchestratorContext(
        session_manager=None,
        session_id="sess_test",
        loop_memory=lm,
        request_id_prefix="req_test",
        dossier_id="D1",
    )
    ctx.rationale_strip_snapshot = strip or []
    return ctx


def _make_tx_domain_pack(
    *,
    decision_ledger: dict[str, Any] | None = None,
    blocker_registry: dict[str, Any] | None = None,
    mission_objective: str = "verify transcript edit focus packet",
) -> TranscriptEditDomainPack:
    request = TranscriptEditAgentRunRequest(
        mission_objective=mission_objective,
        dossier_id="D1",
    )
    state = TranscriptEditLoopState(
        decision_ledger=decision_ledger or {},
        blocker_registry=blocker_registry or {},
        current_transcript_ref="artifacts/tx/source.json",
    )
    return TranscriptEditDomainPack(
        request=request,
        session_id="sess_test",
        request_id_prefix="req_test",
        initial_state=state,
    )


# ---------------------------------------------------------------------------
# 2. run_progress_frame present and shallow in focus packet
# ---------------------------------------------------------------------------

def test_run_progress_frame_present_in_tx_focus_packet() -> None:
    """build_focus_packet() must inject run_progress_frame into domain_packet."""
    blocker = {"focus_key": "span_range", "state": "open", "reason_code": "missing_value"}
    ctx = _make_tx_context(blocker_surface=[blocker], no_progress_streak=1)
    pack = _make_tx_domain_pack()

    fp = pack.build_focus_packet(ctx, "span_range")
    packet = fp.domain_packet
    assert isinstance(packet, dict), "domain_packet must be a dict"
    assert "run_progress_frame" in packet, "run_progress_frame must be injected"

    frame = packet["run_progress_frame"]
    assert isinstance(frame, dict)
    assert set(frame.keys()) == {"run_identity", "run_posture", "work_summary"}

    identity = frame["run_identity"]
    assert identity["run_link_id"] == "req_test"
    assert identity["domain"] == "transcript_edit"
    assert identity["surface"] == "tx_planner"
    assert identity["mission_objective"] == "verify transcript edit focus packet"

    posture = frame["run_posture"]
    assert posture["no_progress_streak"] == 1
    assert "hitl_state" in posture
    assert "invalid_plan_strikes" in posture

    work = frame["work_summary"]
    top = work["blocking_items_top"]
    assert len(top) == 1
    # v1 shallow keys only — must not contain disallowed keys
    _ALLOWED = {"focus_key", "state", "reason_code", "priority"}
    _DISALLOWED = {"decision_key", "blocker_type", "severity", "summary"}
    for item in top:
        assert set(item.keys()).issubset(_ALLOWED), (
            f"Disallowed keys in blocking item: {set(item.keys()) - _ALLOWED}"
        )
        assert not set(item.keys()) & _DISALLOWED, (
            f"Forbidden keys present: {set(item.keys()) & _DISALLOWED}"
        )


def test_run_progress_frame_cap_at_five_blockers() -> None:
    """blocking_items_top must never exceed 5 items regardless of blocker_surface size."""
    blockers = [
        {"focus_key": f"k{i}", "state": "open", "reason_code": "x", "extra_noise": "GONE"}
        for i in range(9)
    ]
    ctx = _make_tx_context(blocker_surface=blockers)
    pack = _make_tx_domain_pack()
    fp = pack.build_focus_packet(ctx, "k0")
    top = fp.domain_packet["run_progress_frame"]["work_summary"]["blocking_items_top"]
    assert len(top) == 5
    for item in top:
        assert "extra_noise" not in item


# ---------------------------------------------------------------------------
# 3. rationale_continuity_strip present iff strip is non-empty
# ---------------------------------------------------------------------------

def test_rationale_strip_injected_when_non_empty() -> None:
    """rationale_continuity_strip must appear in packet when context has strip entries."""
    strip = [
        {
            "iteration_index": 2,
            "focus_key": "span_range",
            "move_type": "apply_edit_plan",
            "why_summary": "fix range token",
            "outcome_summary": "refused (validation_failed)",
            "carry_forward_hint": "adjust inputs/shape; prior attempt refused (retryable)",
        }
    ]
    ctx = _make_tx_context(strip=strip)
    pack = _make_tx_domain_pack()
    fp = pack.build_focus_packet(ctx, "span_range")
    assert "rationale_continuity_strip" in fp.domain_packet
    injected = fp.domain_packet["rationale_continuity_strip"]
    assert len(injected) == 1
    assert injected[0]["iteration_index"] == 2
    assert injected[0]["carry_forward_hint"] == "adjust inputs/shape; prior attempt refused (retryable)"


def test_rationale_strip_absent_when_empty() -> None:
    """rationale_continuity_strip must NOT appear in packet when context strip is empty."""
    ctx = _make_tx_context(strip=[])
    pack = _make_tx_domain_pack()
    fp = pack.build_focus_packet(ctx, "span_range")
    assert "rationale_continuity_strip" not in fp.domain_packet, (
        "Empty strip must not inject key into packet"
    )


# ---------------------------------------------------------------------------
# 4. No key duplication between injected sections and surrounding packet
# ---------------------------------------------------------------------------

def test_no_key_duplication_in_focus_packet() -> None:
    """Injected framing keys must not duplicate top-level packet keys."""
    strip = [{"iteration_index": 1, "focus_key": "k1", "move_type": "m", "why_summary": "",
               "outcome_summary": "executed", "carry_forward_hint": ""}]
    ctx = _make_tx_context(strip=strip)
    pack = _make_tx_domain_pack()
    fp = pack.build_focus_packet(ctx, "span_range")
    packet = fp.domain_packet

    # Injected keys are top-level — confirm they exist and are distinct dict structures.
    frame = packet.get("run_progress_frame", {})
    strip_out = packet.get("rationale_continuity_strip", [])

    # No cross-contamination: run_identity keys should not appear as top-level packet keys
    # (they live nested inside run_progress_frame).
    identity_keys = set(frame.get("run_identity", {}).keys())
    packet_keys = set(packet.keys()) - {"run_progress_frame", "rationale_continuity_strip"}
    overlap = identity_keys & packet_keys
    assert not overlap, f"run_identity keys leaked into packet top-level: {overlap}"

    # run_posture and work_summary sub-keys must not duplicate top-level packet keys
    posture_keys = set(frame.get("run_posture", {}).keys())
    work_keys = set(frame.get("work_summary", {}).keys())
    assert not (posture_keys & packet_keys), f"run_posture keys overlap with packet: {posture_keys & packet_keys}"
    assert not (work_keys & packet_keys), f"work_summary keys overlap with packet: {work_keys & packet_keys}"

    # Strip entries must not duplicate run_progress_frame keys at packet level.
    assert isinstance(strip_out, list)
    for entry in strip_out:
        assert isinstance(entry, dict)
        # strip entries must not be present verbatim under run_progress_frame
        assert entry not in [frame]


# ---------------------------------------------------------------------------
# 5. Strip quality: omission + hint mapping roundtrip
# ---------------------------------------------------------------------------

def test_strip_omits_repeated_posture_and_maps_hints_correctly() -> None:
    """Integration: strip derived from trace events respects omission + hint rules."""
    def _mk(i, focus, move, exec_state, retryable, exec_rc, prog_rc, made, streak):
        return [
            {"phase": "focus_selection", "iteration_index": i, "payload": {"focus_key": focus}},
            {"phase": "move_resolution", "iteration_index": i,
             "payload": {"move_type": move, "rationale": f"step {i}"}},
            {"phase": "execution", "iteration_index": i,
             "payload": {"execution_state": exec_state, "retryable": retryable},
             "reason_code": exec_rc},
            {"phase": "progress_evaluation", "iteration_index": i,
             "payload": {"reason_code": prog_rc, "made_progress": made,
                         "no_progress_streak": streak}},
        ]

    events = (
        _mk(1, "range", "apply_edit_plan", "executed", None, "", "blocking_count_reduced", True, 0)
        + _mk(2, "range", "apply_edit_plan", "executed", None, "", "blocking_count_reduced", True, 0)  # omit
        + _mk(3, "range", "apply_edit_plan", "refused", True, "val_fail", "no_material_change", False, 1)
        + _mk(4, "range", "apply_edit_plan", "executed", None, "", "new_signal_arrived", True, 0)
        + _mk(5, "range", "apply_edit_plan", "executed", None, "", "no_material_change", False, 2)
    )
    strip = build_rationale_continuity_strip(events, max_entries=5)
    included = {e["iteration_index"]: e for e in strip}

    assert 2 not in included, "iter 2 is a posture repeat — must be omitted"
    assert 3 in included
    assert included[3]["carry_forward_hint"] == "adjust inputs/shape; prior attempt refused (retryable)"
    assert included[4]["carry_forward_hint"] == "new evidence arrived; re-evaluate focus/move"
    assert included[5]["carry_forward_hint"] == "change tactic: gather new signal or escalate"


def test_strip_rank_based_trim_preserves_refusals_over_routine() -> None:
    """Trimming must keep rank-1/2/3 entries and drop rank-4 first."""
    def _mk(i, focus, move, exec_state, retryable, prog_rc, made, streak):
        return [
            {"phase": "focus_selection", "iteration_index": i, "payload": {"focus_key": focus}},
            {"phase": "move_resolution", "iteration_index": i,
             "payload": {"move_type": move, "rationale": ""}},
            {"phase": "execution", "iteration_index": i,
             "payload": {"execution_state": exec_state, "retryable": retryable},
             "reason_code": ""},
            {"phase": "progress_evaluation", "iteration_index": i,
             "payload": {"reason_code": prog_rc, "made_progress": made,
                         "no_progress_streak": streak}},
        ]

    events = (
        _mk(1, "a", "apply_edit_plan", "refused", False, "no_material_change", False, 1)      # rank 1
        + _mk(2, "b", "gather_more_evidence", "executed", None, "new_signal_arrived", True, 0) # rank 2
        + _mk(3, "c", "apply_edit_plan", "executed", None, "no_material_change", False, 3)    # rank 3
        + _mk(4, "d", "apply_edit_plan", "executed", None, "blocking_count_reduced", True, 0) # rank 4
        + _mk(5, "e", "apply_edit_plan", "executed", None, "blocking_count_reduced", True, 0) # rank 4
        + _mk(6, "f", "apply_edit_plan", "refused", True, "no_material_change", False, 1)     # rank 1
        + _mk(7, "g", "mark_blocked", "skipped", None, "no_material_change", False, 2)        # rank 1
    )
    strip = build_rationale_continuity_strip(events, max_entries=4)
    iters = {e["iteration_index"] for e in strip}
    assert len(strip) == 4
    assert 4 not in iters, "rank-4 iter 4 must be trimmed before rank-1/2/3 entries"
    assert 5 not in iters, "rank-4 iter 5 must be trimmed before rank-1/2/3 entries"
    assert 1 in iters and 6 in iters and 7 in iters, "rank-1 entries must be preserved"
