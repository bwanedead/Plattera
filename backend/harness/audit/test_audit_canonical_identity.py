"""Phase 4: Canonical event identity — audit lineage tests.

Invariants protected here:
- events.jsonl entries carry run_id, session_id, request_id as top-level fields
- turn_NNNN.json files include canonical lineage fields
- orphaned turn_completed stubs carry canonical identity
- caller-supplied identity fields are not overwritten
- no-op writer accepts canonical identity params without raising
"""

from __future__ import annotations

import json
from pathlib import Path

from harness.audit.run_audit_writer import RunAuditWriter


def test_event_log_carries_canonical_run_lineage(tmp_path: Path) -> None:
    """events.jsonl entries must carry run_id, session_id, request_id as top-level fields."""
    writer = RunAuditWriter(
        tmp_path / "run1",
        run_id="run-canon",
        session_id="sess-canon",
        request_id="req-canon",
    )
    writer.observe_llm_io({"turn_index": 1, "parse_ok": True})
    writer.observe_turn_completed({
        "turn_index": 1,
        "tool_request": None,
        "tool_result_raw": None,
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {},
        "state_patch_feedback": {},
        "terminal_decision": "complete_run",
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    events_path = tmp_path / "run1" / "audit" / "events.jsonl"
    assert events_path.exists()
    lines = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) >= 2
    for entry in lines:
        assert entry.get("run_id") == "run-canon", f"run_id missing or wrong in: {entry}"
        assert entry.get("session_id") == "sess-canon", f"session_id missing or wrong in: {entry}"
        assert entry.get("request_id") == "req-canon", f"request_id missing or wrong in: {entry}"


def test_turn_files_carry_canonical_run_lineage(tmp_path: Path) -> None:
    """turn_NNNN.json files must include run_id, session_id, request_id."""
    writer = RunAuditWriter(
        tmp_path / "run1",
        run_id="run-t",
        session_id="sess-t",
        request_id="req-t",
    )
    writer.observe_llm_io({"turn_index": 2, "parse_ok": True})
    writer.finalize(terminal_class="completed", reason_code="done", iterations=2, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0002.json").read_text())
    assert turn.get("run_id") == "run-t"
    assert turn.get("session_id") == "sess-t"
    assert turn.get("request_id") == "req-t"


def test_turn_completed_stub_carries_canonical_run_lineage(tmp_path: Path) -> None:
    """Orphaned turn_completed stubs (no prior llm_io) must also carry canonical identity."""
    writer = RunAuditWriter(
        tmp_path / "run1",
        run_id="run-stub",
        session_id="sess-stub",
        request_id="req-stub",
    )
    writer.observe_turn_completed({
        "turn_index": 7,
        "tool_request": None,
        "tool_result_raw": None,
        "mission_state_after": None,
        "resolution_state_after": None,
        "latest_refs_after": {},
        "state_patch_feedback": {},
        "terminal_decision": "complete_run",
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=7, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0007.json").read_text())
    assert turn.get("run_id") == "run-stub"
    assert turn.get("session_id") == "sess-stub"
    assert turn.get("request_id") == "req-stub"

    events_path = tmp_path / "run1" / "audit" / "events.jsonl"
    lines = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    for entry in lines:
        assert entry.get("run_id") == "run-stub"


def test_caller_supplied_identity_fields_not_overwritten(tmp_path: Path) -> None:
    """If the incoming record already has identity fields, they must not be overwritten."""
    writer = RunAuditWriter(
        tmp_path / "run1",
        run_id="run-from-constructor",
        session_id="sess-from-constructor",
        request_id="req-from-constructor",
    )
    # Caller explicitly supplies their own session_id (e.g. from LLM turn adapter)
    writer.observe_llm_io({
        "turn_index": 1,
        "session_id": "caller-supplied-session",
        "request_id": "caller-supplied-request",
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    # Caller-supplied values are preserved (not overwritten by constructor values)
    assert turn.get("session_id") == "caller-supplied-session"
    assert turn.get("request_id") == "caller-supplied-request"
    # run_id was not in the caller data, so constructor value stamps it
    assert turn.get("run_id") == "run-from-constructor"


def test_no_op_writer_accepts_canonical_identity_params() -> None:
    """RunAuditWriter(None, ...) must not raise when canonical identity params are supplied."""
    writer = RunAuditWriter(None, run_id="r", session_id="s", request_id="req")
    writer.observe_llm_io({"turn_index": 1})
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])
    # No exception — identity params are silently ignored for no-op instances


def test_event_log_payload_does_not_carry_conflicting_identity(tmp_path: Path) -> None:
    """JSONL payload identity must match the top-level canonical meta (no split lineage).

    Even when a caller supplies different session_id/request_id in the record,
    the events.jsonl payload must carry the canonical values — not the caller's values.
    The caller-supplied values are preserved only in the turn file.
    """
    writer = RunAuditWriter(
        tmp_path / "run1",
        run_id="canonical-run",
        session_id="canonical-sess",
        request_id="canonical-req",
    )
    writer.observe_llm_io({
        "turn_index": 1,
        "session_id": "caller-different-session",
        "request_id": "caller-different-request",
    })
    writer.finalize(terminal_class="completed", reason_code="done", iterations=1, latest_refs={}, trace_events=[])

    # Turn file: caller-supplied values are preserved (fill-gaps behavior)
    turn = json.loads((tmp_path / "run1" / "audit" / "turn_0001.json").read_text())
    assert turn.get("session_id") == "caller-different-session"
    assert turn.get("request_id") == "caller-different-request"

    # JSONL: top-level meta AND payload must both carry canonical values (no split lineage)
    events_path = tmp_path / "run1" / "audit" / "events.jsonl"
    lines = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert lines, "events.jsonl must have at least one entry"
    entry = lines[0]
    # Top-level canonical meta
    assert entry.get("session_id") == "canonical-sess"
    assert entry.get("request_id") == "canonical-req"
    # Payload must also carry canonical values — no split lineage
    payload = entry.get("payload") or {}
    assert payload.get("session_id") == "canonical-sess", \
        f"payload session_id conflicts with canonical meta: {payload.get('session_id')!r}"
    assert payload.get("request_id") == "canonical-req", \
        f"payload request_id conflicts with canonical meta: {payload.get('request_id')!r}"


def test_event_log_kind_field_still_present(tmp_path: Path) -> None:
    """Stamping canonical identity must not drop the existing kind/ts/turn_index fields."""
    writer = RunAuditWriter(
        tmp_path / "run1",
        run_id="run-k",
        session_id="sess-k",
        request_id="req-k",
    )
    writer.observe_llm_io({"turn_index": 3, "parse_ok": True})
    writer.finalize(terminal_class="completed", reason_code="done", iterations=3, latest_refs={}, trace_events=[])

    events_path = tmp_path / "run1" / "audit" / "events.jsonl"
    lines = [json.loads(l) for l in events_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    llm_io_entry = next((e for e in lines if e.get("kind") == "llm_io"), None)
    assert llm_io_entry is not None, "llm_io event missing from events.jsonl"
    assert llm_io_entry.get("turn_index") == 3
    assert llm_io_entry.get("ts") is not None
    # Canonical identity fields are present alongside the existing fields
    assert llm_io_entry.get("run_id") == "run-k"
