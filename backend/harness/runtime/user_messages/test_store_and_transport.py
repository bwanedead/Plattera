"""Tests for the on-disk user-message store + ledger ingestion transport."""

from __future__ import annotations

from pathlib import Path

import services.agent_viewer.identifiers as _ids  # noqa: F401 — sanity import

from harness.runtime.user_messages import store as _store_mod
from harness.runtime.user_messages.store import (
    append_entry,
    list_entries,
    user_messages_path,
)
from harness.runtime.user_messages.transport import poll_user_messages


def _isolate_store(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(_store_mod, "dossiers_artifacts_root", lambda: tmp_path)


def test_append_and_list_roundtrip(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    entry = append_entry(
        loop_kind="harness_cli",
        run_id="r1",
        text="hello agent",
        source="cli",
        metadata={"item_id": "i-1"},
    )
    assert entry["text"] == "hello agent"
    assert entry["source"] == "cli"
    assert entry["message_id"].startswith("user-msg-")
    listed = list_entries(loop_kind="harness_cli", run_id="r1")
    assert len(listed) == 1
    assert listed[0]["message_id"] == entry["message_id"]


def test_append_with_explicit_message_id(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    entry = append_entry(
        loop_kind="harness_cli", run_id="r1",
        text="x", message_id="user-msg-fixed-1",
    )
    assert entry["message_id"] == "user-msg-fixed-1"


def test_append_with_blank_explicit_message_id_generates_id(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    entry = append_entry(
        loop_kind="harness_cli", run_id="r1",
        text="x", message_id="   ",
    )
    assert entry["message_id"].startswith("user-msg-")


def test_append_bounds_text_before_writing_store(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    entry = append_entry(
        loop_kind="harness_cli",
        run_id="r1",
        text="x" * 50_000,
        message_id="user-msg-large",
    )
    assert len(entry["text"]) == 8_192
    assert entry["_bounds"]["text_truncated"] is True
    listed = list_entries(loop_kind="harness_cli", run_id="r1")
    assert len(listed[0]["text"]) == 8_192
    assert listed[0]["_bounds"]["text_truncated"] is True


def test_list_entries_returns_empty_when_no_file(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    assert list_entries(loop_kind="harness_cli", run_id="missing") == []


def test_user_messages_path_under_agent_viewer_root(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    p = user_messages_path(loop_kind="harness_cli", run_id="r1")
    assert str(p).startswith(str(tmp_path))
    assert "agent_viewer" in p.parts
    assert "user_messages" in p.parts
    assert "harness_cli" in p.parts
    assert p.name == "r1.json"


# ---------------------------------------------------------------------------
# transport: poll_user_messages
# ---------------------------------------------------------------------------

def test_poll_ingests_new_entries_into_ledger_with_callback(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="msg-a", message_id="user-msg-a")
    append_entry(loop_kind="lk", run_id="r1", text="msg-b", message_id="user-msg-b")

    seen: list[tuple[str, dict]] = []

    def _on_inbound(mid: str, entry: dict) -> None:
        seen.append((mid, entry))

    new_ledger = poll_user_messages(
        existing_ledger=[],
        loop_kind="lk", run_id="r1", iteration=5,
        on_inbound=_on_inbound,
    )
    assert [e["message_id"] for e in new_ledger] == ["user-msg-a", "user-msg-b"]
    assert [s[0] for s in seen] == ["user-msg-a", "user-msg-b"]
    assert all(e["received_at_iteration"] == 5 for e in new_ledger)


def test_poll_is_idempotent_on_already_recorded_ids(tmp_path, monkeypatch) -> None:
    """Polling twice over the same store does not double-record."""
    _isolate_store(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="msg-a", message_id="user-msg-a")
    first = poll_user_messages(
        existing_ledger=[],
        loop_kind="lk", run_id="r1", iteration=1,
    )
    callback_calls: list[str] = []
    second = poll_user_messages(
        existing_ledger=first,
        loop_kind="lk", run_id="r1", iteration=2,
        on_inbound=lambda mid, _: callback_calls.append(mid),
    )
    assert len(second) == 1  # not doubled
    assert callback_calls == []  # callback not re-fired


def test_poll_picks_up_messages_appended_between_iterations(tmp_path, monkeypatch) -> None:
    """User can inject a new message mid-run; the next poll surfaces it."""
    _isolate_store(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="first", message_id="user-msg-1")
    ledger = poll_user_messages(existing_ledger=[], loop_kind="lk", run_id="r1", iteration=1)
    assert len(ledger) == 1
    # User injects another message between iterations
    append_entry(loop_kind="lk", run_id="r1", text="second", message_id="user-msg-2")
    ledger2 = poll_user_messages(existing_ledger=ledger, loop_kind="lk", run_id="r1", iteration=2)
    assert [e["message_id"] for e in ledger2] == ["user-msg-1", "user-msg-2"]
    assert ledger2[1]["received_at_iteration"] == 2


def test_poll_handles_missing_store_file_gracefully(tmp_path, monkeypatch) -> None:
    _isolate_store(tmp_path, monkeypatch)
    ledger = poll_user_messages(existing_ledger=[], loop_kind="lk", run_id="ghost", iteration=1)
    assert ledger == []


def test_poll_clamps_pathological_text_at_ingest(tmp_path, monkeypatch) -> None:
    """Even if the store has a 50K text blob, the ledger entry is bounded."""
    _isolate_store(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="x" * 50_000, message_id="user-msg-1")
    ledger = poll_user_messages(existing_ledger=[], loop_kind="lk", run_id="r1", iteration=1)
    assert len(ledger[0]["text"]) == 8_192
    assert ledger[0].get("_bounds", {}).get("text_truncated") is True


def test_poll_callback_reports_new_entry_after_ledger_compaction(tmp_path, monkeypatch) -> None:
    """The inbound trace callback must receive the new entry, not the post-clamp tail row."""
    _isolate_store(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="fresh", message_id="user-msg-fresh")
    existing = [
        {
            "message_id": "user-msg-pending",
            "created_at_epoch_seconds": 1,
            "source": "cli",
            "text": "old pending",
            "metadata": {},
            "status": "pending",
            "received_at_iteration": 1,
            "consumed_iteration": None,
            "defer_reason": None,
            "deferred_iteration": None,
        }
    ]
    existing.extend(
        {
            "message_id": f"user-msg-consumed-{i}",
            "created_at_epoch_seconds": i,
            "source": "cli",
            "text": "terminal",
            "metadata": {},
            "status": "consumed",
            "received_at_iteration": i,
            "consumed_iteration": i,
            "defer_reason": None,
            "deferred_iteration": None,
        }
        for i in range(300)
    )
    seen: list[tuple[str, dict]] = []

    ledger = poll_user_messages(
        existing_ledger=existing,
        loop_kind="lk",
        run_id="r1",
        iteration=9,
        on_inbound=lambda mid, entry: seen.append((mid, entry)),
    )

    assert seen == [("user-msg-fresh", next(e for e in ledger if e["message_id"] == "user-msg-fresh"))]
