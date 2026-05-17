"""Tests for the user-to-agent message ledger."""

from __future__ import annotations

from harness.runtime.user_messages.ledger import (
    build_prompt_user_message_view,
    count_consumed,
    count_deferred,
    count_pending,
    get_message,
    make_message_id,
    mark_consumed,
    mark_deferred,
    record_inbound,
    render_user_message_audit_view,
    validate_stored_user_message,
)


def _seed_pending(message_id: str = "user-msg-1", text: str = "fix this", iteration: int = 1):
    ledger, _ = record_inbound(
        [],
        message_id=message_id,
        text=text,
        created_at_epoch_seconds=1000,
        iteration=iteration,
        source="cli",
    )
    return ledger


# ---------------------------------------------------------------------------
# record_inbound
# ---------------------------------------------------------------------------

def test_record_inbound_appends_pending_entry() -> None:
    ledger, appended = record_inbound(
        [],
        message_id="user-msg-1",
        text="hello",
        created_at_epoch_seconds=1000,
        iteration=5,
        source="cli",
    )
    assert appended is True
    assert len(ledger) == 1
    entry = ledger[0]
    assert entry["message_id"] == "user-msg-1"
    assert entry["text"] == "hello"
    assert entry["status"] == "pending"
    assert entry["received_at_iteration"] == 5
    assert entry["source"] == "cli"
    assert entry["consumed_iteration"] is None
    assert entry["defer_reason"] is None


def test_record_inbound_idempotent_on_message_id() -> None:
    """Re-recording the same message_id is a no-op — preserves existing status."""
    ledger = _seed_pending()
    ledger, _, _ = mark_consumed(ledger, message_ids=["user-msg-1"], iteration=2)
    ledger2, appended = record_inbound(
        ledger,
        message_id="user-msg-1",
        text="DIFFERENT",
        created_at_epoch_seconds=9999,
        iteration=10,
    )
    assert appended is False
    # Status preserved, text not overwritten
    assert ledger2 == ledger
    assert ledger2[0]["status"] == "consumed"


def test_record_inbound_bounds_pathological_text() -> None:
    """Inbound normalization clamps text at admission via the shape module."""
    ledger, _ = record_inbound(
        [],
        message_id="user-msg-1",
        text="x" * 20_000,
        created_at_epoch_seconds=1,
        iteration=1,
    )
    entry = ledger[0]
    assert len(entry["text"]) == 8_192
    assert entry.get("_bounds", {}).get("text_truncated") is True


def test_record_inbound_preserves_prior_bounds_markers() -> None:
    ledger, _ = record_inbound(
        [],
        message_id="user-msg-1",
        text="x" * 8_192,
        created_at_epoch_seconds=1,
        iteration=1,
        bounds={"text_truncated": True, "evil": True},
    )
    assert ledger[0]["_bounds"] == {"text_truncated": True}


def test_record_inbound_bounds_message_id_before_idempotency() -> None:
    long_id = "m" * 300
    ledger, appended = record_inbound(
        [],
        message_id=long_id,
        text="first",
        created_at_epoch_seconds=1,
        iteration=1,
    )
    assert appended is True
    assert ledger[0]["message_id"] == "m" * 256
    assert ledger[0]["_bounds"] == {"message_id_truncated": True}

    ledger2, appended2 = record_inbound(
        ledger,
        message_id=long_id,
        text="second",
        created_at_epoch_seconds=2,
        iteration=2,
    )
    assert appended2 is False
    assert ledger2 == ledger


def test_record_inbound_skips_blank_message_id() -> None:
    ledger, appended = record_inbound(
        [],
        message_id="   ",
        text="hi",
        created_at_epoch_seconds=1,
        iteration=1,
    )
    assert appended is False
    assert ledger == []


# ---------------------------------------------------------------------------
# mark_consumed
# ---------------------------------------------------------------------------

def test_mark_consumed_transitions_status_and_records_iteration() -> None:
    ledger = _seed_pending()
    ledger2, matched, unknown = mark_consumed(
        ledger, message_ids=["user-msg-1"], iteration=7,
    )
    assert matched == ["user-msg-1"]
    assert unknown == []
    assert ledger2[0]["status"] == "consumed"
    assert ledger2[0]["consumed_iteration"] == 7


def test_mark_consumed_reports_unknown_ids_for_drift() -> None:
    ledger = _seed_pending()
    _, matched, unknown = mark_consumed(
        ledger, message_ids=["user-msg-1", "user-msg-ghost"], iteration=2,
    )
    assert matched == ["user-msg-1"]
    assert unknown == ["user-msg-ghost"]


def test_mark_consumed_idempotent_on_already_consumed() -> None:
    ledger = _seed_pending()
    ledger, _, _ = mark_consumed(ledger, message_ids=["user-msg-1"], iteration=5)
    ledger2, matched, _ = mark_consumed(ledger, message_ids=["user-msg-1"], iteration=99)
    assert matched == ["user-msg-1"]
    # iteration NOT bumped on already-consumed entries
    assert ledger2[0]["consumed_iteration"] == 5


# ---------------------------------------------------------------------------
# mark_deferred
# ---------------------------------------------------------------------------

def test_mark_deferred_records_reason_and_iteration() -> None:
    ledger = _seed_pending()
    ledger2, matched, unknown = mark_deferred(
        ledger,
        defers=[{"message_id": "user-msg-1", "reason": "scope X is paused"}],
        iteration=3,
    )
    assert matched == ["user-msg-1"]
    assert unknown == []
    entry = ledger2[0]
    assert entry["status"] == "deferred"
    assert entry["defer_reason"] == "scope X is paused"
    assert entry["deferred_iteration"] == 3


def test_mark_deferred_unknown_id_surfaces_as_drift() -> None:
    ledger = _seed_pending()
    _, matched, unknown = mark_deferred(
        ledger,
        defers=[{"message_id": "user-msg-ghost", "reason": "no such msg"}],
        iteration=4,
    )
    assert matched == []
    assert unknown == ["user-msg-ghost"]


def test_mark_deferred_does_not_downgrade_consumed_entries() -> None:
    """An already-consumed entry should not be flipped back to deferred."""
    ledger = _seed_pending()
    ledger, _, _ = mark_consumed(ledger, message_ids=["user-msg-1"], iteration=5)
    ledger2, _, _ = mark_deferred(
        ledger,
        defers=[{"message_id": "user-msg-1", "reason": "ignore me"}],
        iteration=99,
    )
    assert ledger2[0]["status"] == "consumed"  # preserved
    assert ledger2[0]["defer_reason"] is None


def test_consumed_after_deferred_is_allowed() -> None:
    """Defer is 'not yet'; later consuming the message is the normal happy path."""
    ledger = _seed_pending()
    ledger, _, _ = mark_deferred(
        ledger,
        defers=[{"message_id": "user-msg-1", "reason": "wait for hitl"}],
        iteration=3,
    )
    ledger, matched, _ = mark_consumed(ledger, message_ids=["user-msg-1"], iteration=7)
    assert matched == ["user-msg-1"]
    assert ledger[0]["status"] == "consumed"


# ---------------------------------------------------------------------------
# counters + lookup
# ---------------------------------------------------------------------------

def test_counters_distinguish_status_buckets() -> None:
    led = _seed_pending("user-msg-a")
    led, _ = record_inbound(led, message_id="user-msg-b", text="b", created_at_epoch_seconds=1, iteration=2)
    led, _ = record_inbound(led, message_id="user-msg-c", text="c", created_at_epoch_seconds=1, iteration=3)
    led, _, _ = mark_consumed(led, message_ids=["user-msg-a"], iteration=5)
    led, _, _ = mark_deferred(led, defers=[{"message_id": "user-msg-b", "reason": "wait"}], iteration=6)
    assert count_pending(led) == 1
    assert count_consumed(led) == 1
    assert count_deferred(led) == 1


def test_get_message_returns_entry_or_none() -> None:
    led = _seed_pending()
    assert get_message(led, "user-msg-1")["message_id"] == "user-msg-1"
    assert get_message(led, "user-msg-ghost") is None


# ---------------------------------------------------------------------------
# prompt projection — pending always wins
# ---------------------------------------------------------------------------

def test_prompt_view_includes_all_pending() -> None:
    led = _seed_pending("user-msg-a")
    led, _ = record_inbound(led, message_id="user-msg-b", text="b", created_at_epoch_seconds=1, iteration=2)
    view = build_prompt_user_message_view(led)
    assert {v["message_id"] for v in view} == {"user-msg-a", "user-msg-b"}
    for v in view:
        assert v["status"] == "pending"


def test_prompt_view_tail_limits_old_terminal_entries() -> None:
    """Consumed/deferred entries beyond recent_terminal_keep are omitted."""
    led: list = []
    for i in range(8):
        led, _ = record_inbound(
            led, message_id=f"user-msg-{i}", text=f"m{i}",
            created_at_epoch_seconds=i, iteration=i,
        )
    for i in range(8):
        led, _, _ = mark_consumed(led, message_ids=[f"user-msg-{i}"], iteration=10 + i)
    view = build_prompt_user_message_view(led, recent_terminal_keep=3)
    assert len(view) == 3
    # Most recent consumed three: 5, 6, 7
    assert [v["message_id"] for v in view] == ["user-msg-5", "user-msg-6", "user-msg-7"]


def test_prompt_view_truncates_long_text_with_distinct_marker() -> None:
    """A text within admission bound but over display cap gets a separate marker."""
    led, _ = record_inbound(
        [], message_id="user-msg-1",
        text="z" * 2000,
        created_at_epoch_seconds=1, iteration=1,
    )
    view = build_prompt_user_message_view(led, text_max_chars=400)
    response = view[0]
    assert response["_bounds"].get("text_display_truncated") is True
    # Admission bound did NOT fire (2000 < 8192)
    assert "text_truncated" not in response["_bounds"]


# ---------------------------------------------------------------------------
# audit view + admission-bounds preservation
# ---------------------------------------------------------------------------

def test_audit_view_surfaces_admission_bounds() -> None:
    led, _ = record_inbound(
        [], message_id="user-msg-1",
        text="z" * 20_000,  # triggers admission text_truncated
        created_at_epoch_seconds=1, iteration=1,
    )
    view = render_user_message_audit_view(led)
    assert view[0]["_bounds"].get("text_truncated") is True


# ---------------------------------------------------------------------------
# clamp_ledger — pending never dropped
# ---------------------------------------------------------------------------

def test_clamp_keeps_all_pending_even_when_terminal_explodes() -> None:
    """Pending entries must survive even if many terminal entries pile up."""
    from harness.runtime.user_messages.ledger import clamp_ledger
    led: list = []
    for i in range(5):
        led, _ = record_inbound(
            led, message_id=f"pending-{i}", text=f"p{i}",
            created_at_epoch_seconds=i, iteration=i,
        )
    for i in range(300):  # over the cap
        led.append({
            "message_id": f"old-consumed-{i}",
            "created_at_epoch_seconds": i,
            "source": None,
            "text": "x",
            "metadata": {},
            "status": "consumed",
            "received_at_iteration": i,
            "consumed_iteration": i,
            "defer_reason": None,
            "deferred_iteration": None,
        })
    clamped = clamp_ledger(led)
    pending_ids = [e["message_id"] for e in clamped if e["status"] == "pending"]
    assert pending_ids == [f"pending-{i}" for i in range(5)]


# ---------------------------------------------------------------------------
# make_message_id
# ---------------------------------------------------------------------------

def test_make_message_id_has_prefix_and_is_unique() -> None:
    a = make_message_id()
    b = make_message_id()
    assert a.startswith("user-msg-")
    assert b.startswith("user-msg-")
    assert a != b


# ---------------------------------------------------------------------------
# validate_stored_user_message — resume-snapshot validator
# ---------------------------------------------------------------------------

def test_validate_stored_returns_normalized_for_well_formed_row() -> None:
    row = {
        "message_id": "user-msg-1",
        "created_at_epoch_seconds": 1000,
        "source": "cli",
        "text": "hello",
        "metadata": {"k": "v"},
        "status": "pending",
        "received_at_iteration": 1,
        "consumed_iteration": None,
        "deferred_iteration": None,
        "defer_reason": None,
    }
    out = validate_stored_user_message(row)
    assert out is not None
    assert out["message_id"] == "user-msg-1"
    assert out["status"] == "pending"


def test_validate_stored_rejects_missing_message_id() -> None:
    assert validate_stored_user_message({"text": "x", "status": "pending"}) is None


def test_validate_stored_rejects_unknown_status() -> None:
    assert validate_stored_user_message({"message_id": "m", "status": "weird"}) is None


def test_validate_stored_rejects_non_mapping() -> None:
    assert validate_stored_user_message("not-a-dict") is None
    assert validate_stored_user_message(None) is None


def test_validate_stored_drops_unknown_bounds_markers() -> None:
    row = {
        "message_id": "user-msg-1",
        "text": "hello",
        "status": "pending",
        "_bounds": {
            "text_truncated": True,
            "evil_marker": True,
            "metadata_truncated": False,
        },
    }
    out = validate_stored_user_message(row)
    assert out is not None
    assert out["_bounds"] == {"text_truncated": True}


def test_validate_stored_reapplies_message_bounds_for_resume_rows() -> None:
    row = {
        "message_id": "m" * 300,
        "text": "x" * 20_000,
        "source": "s" * 100,
        "metadata": {"blob": "y" * 40_000},
        "status": "pending",
        "_bounds": {"evil": True},
    }
    out = validate_stored_user_message(row)
    assert out is not None
    assert out["message_id"] == "m" * 256
    assert len(out["text"]) == 8_192
    assert out["source"] == "s" * 64
    assert out["metadata"]["_truncated"] is True
    assert out["_bounds"] == {
        "message_id_truncated": True,
        "source_truncated": True,
        "text_truncated": True,
        "metadata_truncated": True,
    }
