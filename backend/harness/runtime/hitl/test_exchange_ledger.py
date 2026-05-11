"""Tests for the durable HITL exchange ledger.

Pure unit tests for ledger operations — outbound, inbound, mark_consumed,
clamp, audit/prompt projections, validation.  No orchestrator coupling.
"""

from __future__ import annotations

import pytest

from harness.runtime.hitl.exchange_ledger import (
    EXCHANGE_ID_PREFIX,
    build_prompt_ledger_view,
    clamp_ledger,
    count_answered_unconsumed,
    count_consumed,
    count_pending,
    get_exchange,
    make_exchange_id,
    mark_consumed,
    record_inbound,
    record_outbound,
    render_ledger_audit_view,
    validate_stored_ledger_entry,
)


# ---------------------------------------------------------------------------
# make_exchange_id
# ---------------------------------------------------------------------------

def test_make_exchange_id_prefixes_prompt_id() -> None:
    assert make_exchange_id("p123") == f"{EXCHANGE_ID_PREFIX}p123"


def test_make_exchange_id_strips_whitespace() -> None:
    assert make_exchange_id("  p1  ") == "hitl:p1"


def test_make_exchange_id_empty_returns_empty() -> None:
    assert make_exchange_id("") == ""
    assert make_exchange_id("   ") == ""


# ---------------------------------------------------------------------------
# record_outbound
# ---------------------------------------------------------------------------

def test_record_outbound_appends_pending_exchange() -> None:
    ledger: list = []
    new_ledger = record_outbound(
        ledger,
        prompt_id="p1",
        request_payload={"message": "Pick one", "choices": ["a", "b"]},
        iteration=5,
        blocking=True,
    )
    assert len(new_ledger) == 1
    entry = new_ledger[0]
    assert entry["prompt_id"] == "p1"
    assert entry["exchange_id"] == "hitl:p1"
    assert entry["status"] == "pending"
    assert entry["blocking"] is True
    assert entry["issued_at_iteration"] == 5
    assert entry["request"] == {"message": "Pick one", "choices": ["a", "b"]}
    assert entry["response"] is None
    assert entry["received_at_iteration"] is None
    assert entry["consumed_at_iteration"] is None


def test_record_outbound_does_not_mutate_input_ledger() -> None:
    ledger: list = []
    record_outbound(ledger, prompt_id="p1", request_payload={"message": "x"}, iteration=1, blocking=False)
    assert ledger == []


def test_record_outbound_idempotent_upsert_preserves_response() -> None:
    """Re-recording outbound for the same prompt_id refreshes request but keeps response/status."""
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "v1"}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "yes"}, iteration=2)
    # Re-record outbound with new request payload (e.g., resume replay)
    ledger = record_outbound(ledger, prompt_id="p1", request_payload={"message": "v2"}, iteration=3, blocking=True)
    entry = get_exchange(ledger, "p1")
    assert entry is not None
    assert entry["request"] == {"message": "v2"}
    assert entry["blocking"] is True
    assert entry["status"] == "answered", "Status must not regress"
    assert entry["response"] == {"choice": "yes"}


def test_record_outbound_empty_prompt_id_returns_unchanged() -> None:
    ledger = record_outbound([], prompt_id="", request_payload={"message": "x"}, iteration=1, blocking=False)
    assert ledger == []


# ---------------------------------------------------------------------------
# record_inbound
# ---------------------------------------------------------------------------

def test_record_inbound_attaches_response_and_marks_answered() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "x"}, iteration=1, blocking=True)
    ledger, newly_answered = record_inbound(
        ledger, prompt_id="p1", response_payload={"choice": "ok", "note": "fine"}, iteration=2
    )
    assert newly_answered is True
    entry = get_exchange(ledger, "p1")
    assert entry["status"] == "answered"
    assert entry["response"] == {"choice": "ok", "note": "fine"}
    assert entry["received_at_iteration"] == 2


def test_record_inbound_idempotent_returns_false_second_time() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "x"}, iteration=1, blocking=False)
    ledger, first = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "a"}, iteration=2)
    ledger, second = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "b"}, iteration=3)
    assert first is True
    assert second is False, "Second inbound for same prompt_id must be no-op"
    entry = get_exchange(ledger, "p1")
    # Original response preserved
    assert entry["response"] == {"choice": "a"}
    assert entry["received_at_iteration"] == 2


def test_record_inbound_synthesizes_stub_when_no_outbound_recorded() -> None:
    """Resume case: feedback arrives but ledger has no recorded outbound — must not drop."""
    ledger, newly_answered = record_inbound(
        [], prompt_id="p1", response_payload={"choice": "yes"}, iteration=5
    )
    assert newly_answered is True
    assert len(ledger) == 1
    entry = ledger[0]
    assert entry["status"] == "answered"
    assert entry["request"] == {}
    assert entry["response"] == {"choice": "yes"}
    assert entry["received_at_iteration"] == 5


def test_record_inbound_does_not_overwrite_consumed() -> None:
    """Once consumed, a late re-poll inbound must not move the entry backward."""
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "a"}, iteration=2)
    ledger, _, _ = mark_consumed(ledger, prompt_ids=("p1",), iteration=3)
    assert get_exchange(ledger, "p1")["status"] == "consumed"
    ledger, newly = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "b"}, iteration=4)
    assert newly is False
    assert get_exchange(ledger, "p1")["status"] == "consumed"
    assert get_exchange(ledger, "p1")["response"] == {"choice": "a"}


# ---------------------------------------------------------------------------
# mark_consumed
# ---------------------------------------------------------------------------

def test_mark_consumed_transitions_status_and_records_iteration() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "ok"}, iteration=2)
    ledger, matched, unknown = mark_consumed(ledger, prompt_ids=("p1",), iteration=3)
    assert matched == ["p1"]
    assert unknown == []
    entry = get_exchange(ledger, "p1")
    assert entry["status"] == "consumed"
    assert entry["consumed_at_iteration"] == 3
    # Response is preserved as durable history.
    assert entry["response"] == {"choice": "ok"}


def test_mark_consumed_preserves_history_does_not_delete() -> None:
    """Marking consumed must not remove the entry from the ledger."""
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "audit-me"}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "yes"}, iteration=2)
    ledger, _, _ = mark_consumed(ledger, prompt_ids=("p1",), iteration=3)
    assert len(ledger) == 1
    entry = get_exchange(ledger, "p1")
    assert entry["request"] == {"message": "audit-me"}
    assert entry["response"] == {"choice": "yes"}


def test_mark_consumed_returns_unknown_for_no_matching_prompt_id() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger, matched, unknown = mark_consumed(ledger, prompt_ids=("p1", "ghost"), iteration=5)
    assert matched == ["p1"]
    assert unknown == ["ghost"]


def test_mark_consumed_idempotent_second_call_does_not_change_iteration() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "a"}, iteration=2)
    ledger, _, _ = mark_consumed(ledger, prompt_ids=("p1",), iteration=3)
    ledger, _, _ = mark_consumed(ledger, prompt_ids=("p1",), iteration=99)
    assert get_exchange(ledger, "p1")["consumed_at_iteration"] == 3


def test_mark_consumed_empty_input_returns_no_change() -> None:
    ledger = [{"prompt_id": "p1", "status": "answered"}]
    new_ledger, matched, unknown = mark_consumed(ledger, prompt_ids=(), iteration=5)
    assert matched == []
    assert unknown == []


# ---------------------------------------------------------------------------
# clamp_ledger — bounded compaction of consumed only
# ---------------------------------------------------------------------------

def test_clamp_ledger_keeps_all_pending_and_answered() -> None:
    """Even way past the cap, pending + answered must never be dropped."""
    ledger = []
    for i in range(40):
        ledger = record_outbound(ledger, prompt_id=f"p{i}", request_payload={}, iteration=i, blocking=False)
    # All 40 are pending — should be retained.
    clamped = clamp_ledger(ledger)
    assert count_pending(clamped) == 40


def test_clamp_ledger_drops_oldest_consumed_only() -> None:
    """Many consumed exchanges should compact down to retention cap."""
    ledger = []
    for i in range(80):
        ledger = record_outbound(ledger, prompt_id=f"p{i}", request_payload={}, iteration=i, blocking=False)
        ledger, _ = record_inbound(ledger, prompt_id=f"p{i}", response_payload={"choice": "x"}, iteration=i)
        ledger, _, _ = mark_consumed(ledger, prompt_ids=(f"p{i}",), iteration=i)
    consumed_after = count_consumed(ledger)
    # All 80 became consumed; clamp should retain at most 64.
    assert consumed_after <= 64, f"Consumed retention cap exceeded: {consumed_after}"
    # Most recent consumed entries should be preserved.
    assert get_exchange(ledger, "p79") is not None


# ---------------------------------------------------------------------------
# build_prompt_ledger_view — Track 3 prompt projection
# ---------------------------------------------------------------------------

def test_prompt_view_includes_pending_with_full_request() -> None:
    ledger = record_outbound(
        [], prompt_id="p1",
        request_payload={"message": "Verify", "choices": ["yes", "no"]},
        iteration=5, blocking=True,
    )
    view = build_prompt_ledger_view(ledger)
    assert len(view) == 1
    assert view[0]["status"] == "pending"
    assert view[0]["request"]["message"] == "Verify"
    assert view[0]["request"]["choices"] == ["yes", "no"]
    assert view[0]["response"] is None


def test_prompt_view_includes_answered_with_full_response() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "Q"}, iteration=1, blocking=False)
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={"choice": "yes", "note": "exact answer"},
        iteration=2,
    )
    view = build_prompt_ledger_view(ledger)
    assert view[0]["status"] == "answered"
    assert view[0]["response"]["choice"] == "yes"
    assert view[0]["response"]["note"] == "exact answer"


def test_prompt_view_keeps_recent_consumed_drops_old() -> None:
    """Only the most recent N consumed entries should appear."""
    ledger = []
    for i in range(10):
        ledger = record_outbound(ledger, prompt_id=f"p{i}", request_payload={}, iteration=i, blocking=False)
        ledger, _ = record_inbound(ledger, prompt_id=f"p{i}", response_payload={"choice": "x"}, iteration=i)
        ledger, _, _ = mark_consumed(ledger, prompt_ids=(f"p{i}",), iteration=i)
    view = build_prompt_ledger_view(ledger, recent_consumed_keep=3)
    consumed_in_view = [v for v in view if v["status"] == "consumed"]
    assert len(consumed_in_view) == 3
    # Oldest (p0..p6) excluded, newest (p7..p9) kept
    consumed_ids = {v["prompt_id"] for v in consumed_in_view}
    assert consumed_ids == {"p7", "p8", "p9"}


def test_prompt_view_truncates_long_message_and_note() -> None:
    long_msg = "x" * 500
    long_note = "y" * 500
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": long_msg}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"note": long_note, "choice": "ok"}, iteration=2)
    view = build_prompt_ledger_view(ledger, message_max_chars=100, note_max_chars=100)
    assert view[0]["request"]["message"].endswith("…")
    assert len(view[0]["request"]["message"]) <= 101
    assert view[0]["response"]["note"].endswith("…")
    assert len(view[0]["response"]["note"]) <= 101


def test_prompt_view_empty_ledger_returns_empty_list() -> None:
    assert build_prompt_ledger_view([]) == []


# ---------------------------------------------------------------------------
# render_ledger_audit_view — Track 5 audit projection
# ---------------------------------------------------------------------------

def test_audit_view_renders_all_required_fields() -> None:
    ledger = record_outbound(
        [], prompt_id="p1",
        request_payload={
            "message": "Confirm boundary",
            "choices": ["accept", "reject"],
            "context": {"foo": "bar"},
            "evidence_refs": ["artifact://x"],
        },
        iteration=10, blocking=True,
    )
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={"choice": "accept", "note": "looks good", "metadata": {"k": "v"}, "submitted_at_epoch_seconds": 1234.0},
        iteration=11,
    )
    view = render_ledger_audit_view(ledger)
    assert len(view) == 1
    e = view[0]
    assert e["exchange_id"] == "hitl:p1"
    assert e["prompt_id"] == "p1"
    assert e["blocking"] is True
    assert e["status"] == "answered"
    assert e["issued_at_iteration"] == 10
    assert e["received_at_iteration"] == 11
    assert e["request"]["choices"] == ["accept", "reject"]
    assert e["request"]["evidence_refs"] == ["artifact://x"]
    assert e["request"]["context"] == {"foo": "bar"}
    assert e["response"]["choice"] == "accept"
    assert e["response"]["note"] == "looks good"
    assert e["response"]["metadata"] == {"k": "v"}
    assert e["response"]["submitted_at_epoch_seconds"] == 1234.0


# ---------------------------------------------------------------------------
# validate_stored_ledger_entry — resume snapshot validation
# ---------------------------------------------------------------------------

def test_validate_accepts_well_formed_entry() -> None:
    raw = {
        "exchange_id": "hitl:p1",
        "prompt_id": "p1",
        "blocking": True,
        "issued_at_iteration": 5,
        "request": {"message": "Q"},
        "response": {"choice": "yes"},
        "received_at_iteration": 6,
        "consumed_at_iteration": 7,
        "status": "consumed",
    }
    out = validate_stored_ledger_entry(raw)
    assert out is not None
    assert out["status"] == "consumed"
    assert out["request"] == {"message": "Q"}


def test_validate_rejects_missing_prompt_id() -> None:
    assert validate_stored_ledger_entry({"status": "pending"}) is None


def test_validate_rejects_invalid_status() -> None:
    assert validate_stored_ledger_entry({"prompt_id": "p1", "status": "garbage"}) is None


def test_validate_rejects_non_mapping() -> None:
    assert validate_stored_ledger_entry("not-a-mapping") is None
    assert validate_stored_ledger_entry(None) is None


def test_validate_synthesizes_exchange_id_when_missing() -> None:
    out = validate_stored_ledger_entry({"prompt_id": "p1", "status": "pending"})
    assert out is not None
    assert out["exchange_id"] == "hitl:p1"


# ---------------------------------------------------------------------------
# Counters
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# record_inbound — defensive normalization of size-unbounded payloads
# ---------------------------------------------------------------------------

def test_record_inbound_clamps_oversized_choice_and_marks_truncated() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    big_choice = "c" * 30_000
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": big_choice}, iteration=2)
    entry = get_exchange(ledger, "p1")
    assert len(entry["response"]["choice"]) == 16_384
    assert entry["response"]["_bounds"]["choice_truncated"] is True


def test_record_inbound_clamps_oversized_note_and_marks_truncated() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    big_note = "n" * 30_000
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"note": big_note, "choice": "ok"}, iteration=2)
    entry = get_exchange(ledger, "p1")
    assert len(entry["response"]["note"]) == 16_384
    assert entry["response"]["_bounds"]["note_truncated"] is True


def test_record_inbound_drops_unknown_fields_and_size_bounds_metadata() -> None:
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    huge_metadata = {"big_blob": "m" * 50_000}
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={
            "choice": "yes",
            "metadata": huge_metadata,
            "stray_field": "drops out",
        },
        iteration=2,
    )
    entry = get_exchange(ledger, "p1")
    response = entry["response"]
    assert "stray_field" not in response
    md = response["metadata"]
    assert md.get("_truncated") is True
    assert response["_bounds"]["metadata_truncated"] is True


# ---------------------------------------------------------------------------
# Audit + prompt projections surface admission-time truncation markers.
# ---------------------------------------------------------------------------

def test_audit_view_carries_admission_bounds_into_response() -> None:
    """The audit projection must expose ``_bounds`` so reviewers see what was clipped."""
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "Q"}, iteration=1, blocking=False)
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={"choice": "yes", "note": "n" * 30_000},
        iteration=2,
    )
    view = render_ledger_audit_view(ledger)
    bounds = view[0]["response"].get("_bounds")
    assert bounds is not None
    assert bounds.get("note_truncated") is True


def test_prompt_view_carries_admission_bounds_so_model_does_not_misread_clipped_text() -> None:
    """Model-facing projection must include truncation markers for clipped fields."""
    ledger = record_outbound([], prompt_id="p1", request_payload={"message": "Q"}, iteration=1, blocking=False)
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={"choice": "c" * 30_000, "note": "n" * 30_000},
        iteration=2,
    )
    view = build_prompt_ledger_view(ledger)
    bounds = view[0]["response"].get("_bounds")
    assert bounds is not None
    assert bounds.get("choice_truncated") is True
    assert bounds.get("note_truncated") is True


def test_prompt_view_marks_display_truncation_separately_from_admission() -> None:
    """A short admission-bounded note that gets *display*-clipped in the prompt view
    must surface a distinct marker so the model can tell the two layers apart."""
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    # Note is well within admission bound (16384) but exceeds prompt display cap.
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={"choice": "y", "note": "z" * 800},
        iteration=2,
    )
    view = build_prompt_ledger_view(ledger, note_max_chars=400)
    response_view = view[0]["response"]
    # Display truncation marker is present and distinct from admission marker.
    assert response_view["_bounds"].get("note_display_truncated") is True
    # Admission was not truncated (note < 16384), so admission marker absent.
    assert "note_truncated" not in response_view["_bounds"]


def test_admission_bounds_survive_record_inbound_into_audit_and_prompt_view() -> None:
    """End-to-end: payload normalized at admission must keep _bounds through ledger
    storage, audit view, and prompt view — defensive re-normalization in
    ``record_inbound`` must not erase prior truncation markers.

    This pins the regression for the bug where the second normalization pass
    saw already-clipped short strings, found no new truncation, and silently
    dropped the ``_bounds`` block before storing in the ledger.
    """
    from harness.runtime.hitl.feedback_shape import normalize_hitl_feedback

    # 1. Simulate transport-side admission: large note clipped, _bounds set.
    raw_from_feedback_store = {"prompt_id": "p1", "choice": "yes", "note": "n" * 30_000}
    admission_normalized = normalize_hitl_feedback(raw_from_feedback_store)
    assert admission_normalized["_bounds"]["note_truncated"] is True
    # The value handed off to the ledger callback is now short — re-normalization
    # would not detect any new truncation.
    assert len(admission_normalized["note"]) == 16_384

    # 2. Ledger receives the already-bounded payload (callback path).
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload=admission_normalized, iteration=2)

    # 3. Stored ledger entry must still carry the truncation marker.
    stored = get_exchange(ledger, "p1")["response"]
    assert stored["_bounds"]["note_truncated"] is True, (
        "Defensive re-normalization in record_inbound must preserve admission-time _bounds"
    )

    # 4. Audit view must surface it.
    audit = render_ledger_audit_view(ledger)
    assert audit[0]["response"]["_bounds"]["note_truncated"] is True

    # 5. Prompt view must surface it.
    prompt = build_prompt_ledger_view(ledger)
    assert prompt[0]["response"]["_bounds"]["note_truncated"] is True


def test_prompt_view_no_bounds_when_no_truncation_at_all() -> None:
    """Clean short payloads carry no _bounds key at all — model sees data as-is."""
    ledger = record_outbound([], prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger, _ = record_inbound(
        ledger, prompt_id="p1",
        response_payload={"choice": "yes", "note": "short"},
        iteration=2,
    )
    view = build_prompt_ledger_view(ledger)
    assert "_bounds" not in view[0]["response"]


def test_counters_distinguish_status_buckets() -> None:
    ledger = []
    ledger = record_outbound(ledger, prompt_id="p1", request_payload={}, iteration=1, blocking=False)
    ledger = record_outbound(ledger, prompt_id="p2", request_payload={}, iteration=2, blocking=False)
    ledger, _ = record_inbound(ledger, prompt_id="p1", response_payload={"choice": "a"}, iteration=3)
    ledger, _, _ = mark_consumed(ledger, prompt_ids=("p1",), iteration=4)
    assert count_pending(ledger) == 1
    assert count_answered_unconsumed(ledger) == 0
    assert count_consumed(ledger) == 1
    # Add one more answered-unconsumed
    ledger, _ = record_inbound(ledger, prompt_id="p2", response_payload={"choice": "b"}, iteration=5)
    assert count_answered_unconsumed(ledger) == 1
