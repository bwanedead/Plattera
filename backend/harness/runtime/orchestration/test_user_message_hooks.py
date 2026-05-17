"""Tests for the user-message orchestrator hooks (poll + consume/defer + trace)."""

from __future__ import annotations

from pathlib import Path

from harness.runtime.user_messages import store as _store_mod

from harness.runtime.memory import LoopMemoryState
from harness.runtime.orchestration.trace_collector import KernelTraceCollector
from harness.runtime.orchestration.user_message_hooks import (
    poll_and_record_user_messages,
    record_consumed_and_deferred_user_messages,
)
from harness.runtime.user_messages.store import append_entry


def _isolate(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(_store_mod, "dossiers_artifacts_root", lambda: tmp_path)


def _events_of_kind(tracer: KernelTraceCollector, kind: str) -> list[dict]:
    return [e.payload | {"event_kind": e.event_kind} for e in tracer._events if e.event_kind == kind]


def test_poll_records_inbound_into_ledger_and_emits_trace_per_new_message(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="msg-a", message_id="user-msg-a")
    append_entry(loop_kind="lk", run_id="r1", text="msg-b", message_id="user-msg-b")

    mem = LoopMemoryState()
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="r1")

    poll_and_record_user_messages(
        loop_memory=mem, tracer=tracer, iteration=3,
        loop_kind="lk", run_id="r1",
    )

    assert [e["message_id"] for e in mem.continuity.user_message_ledger] == ["user-msg-a", "user-msg-b"]
    events = _events_of_kind(tracer, "user_message_inbound")
    assert [e["message_id"] for e in events] == ["user-msg-a", "user-msg-b"]
    # Trace event carries the bounded payload
    assert events[0]["message"]["text"] == "msg-a"


def test_poll_does_not_re_emit_trace_for_already_recorded_messages(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="msg-a", message_id="user-msg-a")
    mem = LoopMemoryState()
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="r1")

    poll_and_record_user_messages(
        loop_memory=mem, tracer=tracer, iteration=1, loop_kind="lk", run_id="r1",
    )
    poll_and_record_user_messages(
        loop_memory=mem, tracer=tracer, iteration=2, loop_kind="lk", run_id="r1",
    )

    events = _events_of_kind(tracer, "user_message_inbound")
    assert len(events) == 1


def test_record_consumed_marks_ledger_and_emits_summary_trace(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    append_entry(loop_kind="lk", run_id="r1", text="msg-a", message_id="user-msg-a")
    append_entry(loop_kind="lk", run_id="r1", text="msg-b", message_id="user-msg-b")
    mem = LoopMemoryState()
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="r1")
    poll_and_record_user_messages(
        loop_memory=mem, tracer=tracer, iteration=1, loop_kind="lk", run_id="r1",
    )

    record_consumed_and_deferred_user_messages(
        loop_memory=mem, tracer=tracer, iteration=2,
        consumed_ids=("user-msg-a",),
        defers=({"message_id": "user-msg-b", "reason": "out of scope"},),
    )

    ledger = mem.continuity.user_message_ledger
    consumed = next(e for e in ledger if e["message_id"] == "user-msg-a")
    deferred = next(e for e in ledger if e["message_id"] == "user-msg-b")
    assert consumed["status"] == "consumed"
    assert consumed["consumed_iteration"] == 2
    assert deferred["status"] == "deferred"
    assert deferred["defer_reason"] == "out of scope"

    events = _events_of_kind(tracer, "user_message_consumed")
    assert len(events) == 1
    assert events[0]["consumed_message_ids"] == ["user-msg-a"]
    assert events[0]["deferred"] == [{"message_id": "user-msg-b", "reason": "out of scope"}]


def test_record_consumed_with_unknown_id_surfaces_drift_counter(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    mem = LoopMemoryState()
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="r1")

    record_consumed_and_deferred_user_messages(
        loop_memory=mem, tracer=tracer, iteration=2,
        consumed_ids=("user-msg-ghost",),
        defers=(),
    )
    assert mem.continuity.user_message_consumed_unknown_count == 1
    events = _events_of_kind(tracer, "user_message_consumed")
    assert events[0]["unknown_message_ids"] == ["user-msg-ghost"]


def test_no_op_when_neither_consumed_nor_deferred(tmp_path, monkeypatch) -> None:
    _isolate(tmp_path, monkeypatch)
    mem = LoopMemoryState()
    tracer = KernelTraceCollector(session_id="s", request_id="r", run_id="r1")
    record_consumed_and_deferred_user_messages(
        loop_memory=mem, tracer=tracer, iteration=2, consumed_ids=(), defers=(),
    )
    # No trace event, no ledger change, no drift count
    assert mem.continuity.user_message_ledger == []
    assert mem.continuity.user_message_consumed_unknown_count == 0
    assert not _events_of_kind(tracer, "user_message_consumed")
