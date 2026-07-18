"""Deterministic coverage for the generic agent-result-view contract."""

from __future__ import annotations

import ast
import json
from pathlib import Path

from harness.execution.agent_result_view import (
    AGENT_RESULT_VIEW_SCHEMA_VERSION,
    MAX_AGENT_RESULT_VIEW_CHARS,
    AgentResultView,
    AgentResultViewOmission,
    agent_result_view_omission_to_wire,
    agent_result_view_to_wire,
    build_agent_result_view,
    measure_agent_result_view_chars,
    parse_agent_result_view,
)
from harness.execution.contracts import (
    ActionDispatchResult,
    ExecutionSessionStartRequest,
    ExecutionState,
    ExecutionStepRequest,
)
from harness.execution.executor import ExecutionExecutor
from harness.execution.persistence import JsonFileExecutionPersistence
from harness.execution.session import ExecutionSessionManager
from harness.execution.session_wire import execution_session_from_wire, execution_session_to_wire
from harness.execution.wire_codec import (
    action_dispatch_result_from_wire,
    action_dispatch_result_to_wire,
)


def _valid_raw(
    *,
    payload: dict | None = None,
    continuity_key: str | None = "deed_to_ir:current_mapping_review",
    schema_id: str = "deed_to_ir.mapping_review.v1",
) -> dict:
    raw: dict = {
        "schema_version": AGENT_RESULT_VIEW_SCHEMA_VERSION,
        "schema_id": schema_id,
        "payload": payload if payload is not None else {"summary": "ok"},
    }
    if continuity_key is not None:
        raw["continuity_key"] = continuity_key
    return raw


def _envelope_at_char_budget(target_chars: int) -> dict:
    """Build a valid raw envelope whose compact framing is exactly ``target_chars``."""
    base = _valid_raw(payload={"pad": ""}, continuity_key=None)
    overhead = measure_agent_result_view_chars(base)
    assert overhead < target_chars
    pad_len = target_chars - overhead
    candidate = _valid_raw(payload={"pad": "x" * pad_len}, continuity_key=None)
    observed = measure_agent_result_view_chars(candidate)
    assert observed == target_chars, (observed, target_chars)
    return candidate


def test_valid_envelope_construction_and_wire_shape() -> None:
    view, omitted = build_agent_result_view(
        schema_id="deed_to_ir.mapping_review.v1",
        payload={"summary": "ok"},
        continuity_key="deed_to_ir:current_mapping_review",
    )
    assert omitted is None
    assert view is not None
    assert agent_result_view_to_wire(view) == {
        "schema_version": "agent_result_view.v1",
        "schema_id": "deed_to_ir.mapping_review.v1",
        "payload": {"summary": "ok"},
        "continuity_key": "deed_to_ir:current_mapping_review",
    }


def test_mapping_handler_coerces_valid_view() -> None:
    executor = ExecutionExecutor()

    def _handler(request: ExecutionStepRequest):
        return {
            "executed": True,
            "outputs": {"status": "ok"},
            "agent_result_view": _valid_raw(),
        }

    executor.register("tool_a", _handler)
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_a", idempotency_key="k1")
    )
    assert result.executed is True
    assert result.outputs == {"status": "ok"}
    assert result.agent_result_view is not None
    assert result.agent_result_view.schema_id == "deed_to_ir.mapping_review.v1"
    assert result.agent_result_view_omitted is None


def test_typed_result_accepts_valid_view_directly() -> None:
    view, omitted = build_agent_result_view(
        schema_id="test.view.v1",
        payload={"n": 1},
        continuity_key="test:key",
    )
    assert omitted is None
    assert view is not None
    executor = ExecutionExecutor()
    executor.register(
        "tool_b",
        lambda request: ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            idempotency_key=request.idempotency_key,
            agent_result_view=view,
        ),
    )
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_b", idempotency_key="k1")
    )
    assert result.agent_result_view == view
    assert result.agent_result_view_omitted is None


def test_typed_invalid_view_becomes_omission_without_changing_semantics() -> None:
    evidence = ({"ref_id": "img-1", "b64": "AAAA", "media_type": "image/png"},)
    executor = ExecutionExecutor()
    executor.register(
        "tool_typed_bad",
        lambda request: ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs={"status": "ok"},
            artifact_refs=("artifact://a",),
            idempotency_key=request.idempotency_key,
            image_evidence=evidence,
            agent_result_view=AgentResultView(
                schema_version="agent_result_view.v0",
                schema_id="test.view.v1",
                payload={"x": 1},
            ),
        ),
    )
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_typed_bad", idempotency_key="k1")
    )
    assert result.executed is True
    assert result.refusal is None
    assert result.outputs == {"status": "ok"}
    assert result.artifact_refs == ("artifact://a",)
    assert result.image_evidence == evidence
    assert result.agent_result_view is None
    assert result.agent_result_view_omitted is not None
    assert result.agent_result_view_omitted.reason == "unsupported_schema_version"


def test_typed_oversized_view_becomes_view_budget_omission() -> None:
    oversized = AgentResultView(
        schema_version=AGENT_RESULT_VIEW_SCHEMA_VERSION,
        schema_id="test.view.v1",
        payload={"pad": "x" * 20_000},
    )
    executor = ExecutionExecutor()
    executor.register(
        "tool_typed_big",
        lambda request: ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            idempotency_key=request.idempotency_key,
            agent_result_view=oversized,
        ),
    )
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_typed_big", idempotency_key="k1")
    )
    assert result.executed is True
    assert result.agent_result_view is None
    assert result.agent_result_view_omitted is not None
    assert result.agent_result_view_omitted.reason == "view_budget"


def test_both_view_and_omission_normalize_to_invalid_shape() -> None:
    view, omitted = parse_agent_result_view(_valid_raw())
    assert omitted is None and view is not None
    result = ActionDispatchResult(
        action_id="tool_both",
        executed=True,
        outputs={"ok": True},
        agent_result_view=view,
        agent_result_view_omitted=AgentResultViewOmission(reason="view_budget", observed_chars=1, maximum_chars=1),
    )
    executor = ExecutionExecutor()
    executor.register("tool_both", lambda request: result)
    coerced = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_both", idempotency_key="k1")
    )
    assert coerced.executed is True
    assert coerced.outputs == {"ok": True}
    assert coerced.agent_result_view is None
    assert coerced.agent_result_view_omitted is not None
    assert coerced.agent_result_view_omitted.reason == "invalid_shape"

    wire = action_dispatch_result_to_wire(result)
    assert "agent_result_view" not in wire
    assert wire.get("agent_result_view_omitted", {}).get("reason") == "invalid_shape"

    restored = action_dispatch_result_from_wire(
        {
            "action_id": "tool_both",
            "executed": True,
            "reason_codes": [],
            "outputs": {"ok": True},
            "refusal": None,
            "artifact_refs": [],
            "idempotency_key": "",
            "agent_result_view": agent_result_view_to_wire(view),
            "agent_result_view_omitted": {"reason": "view_budget", "observed_chars": 1, "maximum_chars": 1},
        }
    )
    assert restored is not None
    assert restored.agent_result_view is None
    assert restored.agent_result_view_omitted is not None
    assert restored.agent_result_view_omitted.reason == "invalid_shape"


def test_envelope_exactly_at_budget_is_retained() -> None:
    raw = _envelope_at_char_budget(MAX_AGENT_RESULT_VIEW_CHARS)
    view, omitted = parse_agent_result_view(raw)
    assert omitted is None
    assert view is not None
    assert measure_agent_result_view_chars(agent_result_view_to_wire(view)) == MAX_AGENT_RESULT_VIEW_CHARS


def test_envelope_one_char_over_budget_is_omitted() -> None:
    raw = _envelope_at_char_budget(MAX_AGENT_RESULT_VIEW_CHARS + 1)
    view, omitted = parse_agent_result_view(raw)
    assert view is None
    assert omitted is not None
    assert omitted.reason == "view_budget"
    assert omitted.observed_chars == MAX_AGENT_RESULT_VIEW_CHARS + 1
    assert omitted.maximum_chars == MAX_AGENT_RESULT_VIEW_CHARS


def test_invalid_schema_version() -> None:
    raw = _valid_raw()
    raw["schema_version"] = "agent_result_view.v0"
    view, omitted = parse_agent_result_view(raw)
    assert view is None
    assert omitted is not None
    assert omitted.reason == "unsupported_schema_version"


def test_blank_or_invalid_schema_id() -> None:
    for bad in ("", "   ", None, 12):
        raw = _valid_raw()
        raw["schema_id"] = bad  # type: ignore[assignment]
        view, omitted = parse_agent_result_view(raw)
        assert view is None
        assert omitted is not None
        assert omitted.reason == "invalid_shape"


def test_invalid_continuity_key() -> None:
    for bad in ("", "   ", 7):
        raw = _valid_raw()
        raw["continuity_key"] = bad  # type: ignore[assignment]
        view, omitted = parse_agent_result_view(raw)
        assert view is None
        assert omitted is not None
        assert omitted.reason == "invalid_shape"


def test_non_object_payload() -> None:
    raw = _valid_raw()
    raw["payload"] = ["not", "an", "object"]
    view, omitted = parse_agent_result_view(raw)
    assert view is None
    assert omitted is not None
    assert omitted.reason == "invalid_shape"


def test_nested_non_json_value() -> None:
    raw = _valid_raw(payload={"blob": b"bytes"})
    view, omitted = parse_agent_result_view(raw)
    assert view is None
    assert omitted is not None
    assert omitted.reason == "not_json_safe"


def test_tuple_payload_rejected_as_not_json_safe() -> None:
    view, omitted = parse_agent_result_view(_valid_raw(payload={"items": (1, 2)}))
    assert view is None
    assert omitted is not None
    assert omitted.reason == "not_json_safe"


def test_unknown_envelope_field_rejected() -> None:
    raw = _valid_raw()
    raw["associated_artifact_refs"] = ["artifact://x"]
    view, omitted = parse_agent_result_view(raw)
    assert view is None
    assert omitted is not None
    assert omitted.reason == "invalid_shape"


def test_builder_returns_omission_for_malformed_payload() -> None:
    view, omitted = build_agent_result_view(schema_id="test.view.v1", payload=object())  # type: ignore[arg-type]
    assert view is None
    assert omitted is not None
    assert omitted.reason == "invalid_shape"


def test_nan_and_infinity_rejected() -> None:
    for bad in (float("nan"), float("inf"), float("-inf")):
        view, omitted = parse_agent_result_view(_valid_raw(payload={"n": bad}))
        assert view is None
        assert omitted is not None
        assert omitted.reason == "not_json_safe"


def test_invalid_view_omitted_atomically() -> None:
    raw = _valid_raw(payload={"keep": "me"})
    raw["schema_version"] = "nope"
    view, omitted = parse_agent_result_view(raw)
    assert view is None
    assert omitted is not None
    wire = agent_result_view_omission_to_wire(omitted)
    assert "payload" not in wire
    assert "keep" not in str(wire)


def test_invalid_view_does_not_change_success_semantics() -> None:
    executor = ExecutionExecutor()

    def _handler(request: ExecutionStepRequest):
        return {
            "executed": True,
            "outputs": {"status": "ok"},
            "artifact_refs": ["artifact://a"],
            "agent_result_view": {"schema_version": "bad", "schema_id": "x", "payload": {}},
        }

    executor.register("tool_c", _handler)
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_c", idempotency_key="k1")
    )
    assert result.executed is True
    assert result.refusal is None
    assert result.outputs == {"status": "ok"}
    assert result.artifact_refs == ("artifact://a",)
    assert result.agent_result_view is None
    assert result.agent_result_view_omitted is not None
    assert result.agent_result_view_omitted.reason == "unsupported_schema_version"


def test_valid_view_wire_round_trip() -> None:
    view, omitted = parse_agent_result_view(_valid_raw())
    assert omitted is None and view is not None
    result = ActionDispatchResult(
        action_id="tool_d",
        executed=True,
        outputs={"x": 1},
        agent_result_view=view,
    )
    restored = action_dispatch_result_from_wire(action_dispatch_result_to_wire(result))
    assert restored is not None
    assert restored.agent_result_view == view
    assert restored.agent_result_view_omitted is None
    assert restored.outputs == {"x": 1}


def test_omission_marker_wire_round_trip() -> None:
    result = ActionDispatchResult(
        action_id="tool_e",
        executed=True,
        agent_result_view_omitted=AgentResultViewOmission(
            reason="view_budget",
            observed_chars=12001,
            maximum_chars=12000,
        ),
    )
    restored = action_dispatch_result_from_wire(action_dispatch_result_to_wire(result))
    assert restored is not None
    assert restored.agent_result_view is None
    assert restored.agent_result_view_omitted == result.agent_result_view_omitted


def test_execution_session_wire_round_trip() -> None:
    view, omitted = parse_agent_result_view(_valid_raw())
    assert omitted is None and view is not None
    executor = ExecutionExecutor()
    executor.register(
        "tool_f",
        lambda request: ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            idempotency_key=request.idempotency_key,
            agent_result_view=view,
        ),
    )
    mgr = ExecutionSessionManager(executor=executor)
    start = mgr.start_session(ExecutionSessionStartRequest(run_id="r1", session_id="s-view"))
    mgr.step(
        ExecutionStepRequest(
            session_id=start.session_id,
            action_id="tool_f",
            idempotency_key="ik-view",
        )
    )
    session, err = execution_session_from_wire(execution_session_to_wire(mgr.sessions[start.session_id]))
    assert err is None and session is not None
    assert session.last_result_by_key["ik-view"].agent_result_view == view


def test_json_session_persistence_round_trip(tmp_path: Path) -> None:
    view, omitted = parse_agent_result_view(_valid_raw())
    assert omitted is None and view is not None
    persistence = JsonFileExecutionPersistence(tmp_path)
    manager = ExecutionSessionManager(persistence=persistence)
    manager.start_session(ExecutionSessionStartRequest(run_id="r1", session_id="s-persist"))
    manager.executor.register(
        "tool_g",
        lambda request: {
            "executed": True,
            "outputs": {"ok": True},
            "agent_result_view": agent_result_view_to_wire(view),
        },
    )
    manager.step(
        ExecutionStepRequest(session_id="s-persist", action_id="tool_g", idempotency_key="ik-p")
    )
    ref = persistence.save_session(manager.sessions["s-persist"])
    loaded = persistence.load_session(ref)
    assert loaded.last_result_by_key["ik-p"].agent_result_view == view
    assert loaded.last_result_by_key["ik-p"].outputs == {"ok": True}

    written = json.loads(Path(ref).read_text(encoding="utf-8"))
    result_json = written["records"][0]["result"]
    assert "agent_result_view_omitted" not in result_json
    assert result_json["agent_result_view"] == {
        "schema_version": "agent_result_view.v1",
        "schema_id": "deed_to_ir.mapping_review.v1",
        "payload": {"summary": "ok"},
        "continuity_key": "deed_to_ir:current_mapping_review",
    }


def test_accepted_payload_survives_json_persistence_exactly(tmp_path: Path) -> None:
    payload = {"items": [1, 2, {"nested": True}], "note": None, "ok": True}
    view, omitted = build_agent_result_view(
        schema_id="test.view.v1",
        payload=payload,
        continuity_key=None,
    )
    assert omitted is None and view is not None
    persistence = JsonFileExecutionPersistence(tmp_path)
    manager = ExecutionSessionManager(persistence=persistence)
    manager.start_session(ExecutionSessionStartRequest(run_id="r1", session_id="s-exact"))
    manager.executor.register(
        "tool_exact",
        lambda request: ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            idempotency_key=request.idempotency_key,
            agent_result_view=view,
        ),
    )
    manager.step(
        ExecutionStepRequest(session_id="s-exact", action_id="tool_exact", idempotency_key="ik-exact")
    )
    ref = persistence.save_session(manager.sessions["s-exact"])
    loaded = persistence.load_session(ref)
    assert loaded.last_result_by_key["ik-exact"].agent_result_view is not None
    assert loaded.last_result_by_key["ik-exact"].agent_result_view.payload == payload
    written = json.loads(Path(ref).read_text(encoding="utf-8"))
    assert written["records"][0]["result"]["agent_result_view"]["payload"] == payload


def test_persistence_both_fields_writes_only_invalid_shape_omission(tmp_path: Path) -> None:
    view, omitted = parse_agent_result_view(_valid_raw(continuity_key=None))
    assert omitted is None and view is not None
    persistence = JsonFileExecutionPersistence(tmp_path)
    manager = ExecutionSessionManager(persistence=persistence)
    manager.start_session(ExecutionSessionStartRequest(run_id="r1", session_id="s-both"))
    contradictory = ActionDispatchResult(
        action_id="tool_both_persist",
        executed=True,
        idempotency_key="ik-both",
        agent_result_view=view,
        agent_result_view_omitted=AgentResultViewOmission(
            reason="view_budget",
            observed_chars=12001,
            maximum_chars=12000,
        ),
    )
    manager.executor.register("tool_both_persist", lambda request: contradictory)
    manager.step(
        ExecutionStepRequest(
            session_id="s-both",
            action_id="tool_both_persist",
            idempotency_key="ik-both",
        )
    )
    ref = persistence.save_session(manager.sessions["s-both"])
    written = json.loads(Path(ref).read_text(encoding="utf-8"))
    result_json = written["records"][0]["result"]
    assert "agent_result_view" not in result_json
    assert result_json["agent_result_view_omitted"] == {"reason": "invalid_shape"}
    loaded = persistence.load_session(ref)
    assert loaded.last_result_by_key["ik-both"].agent_result_view is None
    assert loaded.last_result_by_key["ik-both"].agent_result_view_omitted is not None
    assert loaded.last_result_by_key["ik-both"].agent_result_view_omitted.reason == "invalid_shape"


def test_old_session_files_still_load(tmp_path: Path) -> None:
    path = tmp_path / "sessions" / "legacy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "session_id": "legacy",
                "run_id": "run-legacy",
                "completed_idempotency_keys": ["ik-legacy"],
                "run_artifact": {
                    "run_id": "run-legacy",
                    "session_id": "legacy",
                    "latest_refs": {},
                    "history": [],
                },
                "records": [
                    {
                        "session_id": "legacy",
                        "run_id": "run-legacy",
                        "request": {
                            "session_id": "legacy",
                            "action_id": "tool_h",
                            "inputs": {},
                            "idempotency_key": "ik-legacy",
                            "run_id": "run-legacy",
                        },
                        "result": {
                            "action_id": "tool_h",
                            "executed": True,
                            "reason_codes": [],
                            "outputs": {"legacy": True},
                            "refusal": None,
                            "artifact_refs": [],
                            "idempotency_key": "ik-legacy",
                            "image_evidence": [],
                        },
                    }
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    loaded = JsonFileExecutionPersistence(tmp_path).load_session(str(path))
    assert loaded.last_result_by_key["ik-legacy"].outputs == {"legacy": True}
    assert loaded.last_result_by_key["ik-legacy"].agent_result_view is None
    assert loaded.last_result_by_key["ik-legacy"].agent_result_view_omitted is None


def test_malformed_persisted_omission_does_not_crash() -> None:
    restored = action_dispatch_result_from_wire(
        {
            "action_id": "tool_omission_bad",
            "executed": True,
            "reason_codes": [],
            "outputs": {"still": "here"},
            "refusal": None,
            "artifact_refs": [],
            "idempotency_key": "ik-omission-bad",
            "agent_result_view_omitted": {"reason": "not_a_real_reason", "extra": True},
        }
    )
    assert restored is not None
    assert restored.outputs == {"still": "here"}
    assert restored.agent_result_view is None
    assert restored.agent_result_view_omitted is not None
    assert restored.agent_result_view_omitted.reason == "invalid_shape"


def test_older_records_without_view_fields_remain_compatible() -> None:
    legacy = {
        "action_id": "tool_h",
        "executed": True,
        "reason_codes": [],
        "outputs": {"legacy": True},
        "refusal": None,
        "artifact_refs": ["artifact://legacy"],
        "idempotency_key": "ik-legacy",
    }
    restored = action_dispatch_result_from_wire(legacy)
    assert restored is not None
    assert restored.agent_result_view is None
    assert restored.agent_result_view_omitted is None
    assert restored.outputs == {"legacy": True}
    assert restored.artifact_refs == ("artifact://legacy",)


def test_malformed_persisted_view_does_not_invalidate_action_result() -> None:
    raw = {
        "action_id": "tool_i",
        "executed": True,
        "reason_codes": [],
        "outputs": {"still": "here"},
        "refusal": None,
        "artifact_refs": [],
        "idempotency_key": "ik-bad",
        "agent_result_view": "not-an-object",
    }
    restored = action_dispatch_result_from_wire(raw)
    assert restored is not None
    assert restored.executed is True
    assert restored.outputs == {"still": "here"}
    assert restored.agent_result_view is None
    assert restored.agent_result_view_omitted is not None
    assert restored.agent_result_view_omitted.reason == "invalid_shape"


def test_idempotent_dedupe_retains_same_view() -> None:
    view, omitted = parse_agent_result_view(_valid_raw())
    assert omitted is None and view is not None
    calls: list[str] = []
    manager = ExecutionSessionManager()
    manager.start_session(ExecutionSessionStartRequest(run_id="r1", session_id="s-dedupe"))
    manager.executor.register(
        "tool_j",
        lambda request: calls.append(request.action_id)
        or ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            idempotency_key=request.idempotency_key,
            agent_result_view=view,
        ),
    )
    first = manager.step(
        ExecutionStepRequest(session_id="s-dedupe", action_id="tool_j", idempotency_key="same")
    )
    second = manager.step(
        ExecutionStepRequest(session_id="s-dedupe", action_id="tool_j", idempotency_key="same")
    )
    assert first.execution_state == ExecutionState.EXECUTED
    assert second.execution_state == ExecutionState.DEDUPED
    assert calls == ["tool_j"]
    assert second.record is not None
    assert second.record.result.agent_result_view == view


def test_image_evidence_not_moved_into_view_automatically() -> None:
    executor = ExecutionExecutor()
    evidence = ({"ref_id": "img-1", "b64": "AAAA", "media_type": "image/png"},)

    def _handler(request: ExecutionStepRequest):
        return {
            "executed": True,
            "outputs": {"status": "ok"},
            "image_evidence": list(evidence),
            "agent_result_view": _valid_raw(payload={"note": "text-only"}),
        }

    executor.register("tool_k", _handler)
    result = executor.execute(
        ExecutionStepRequest(session_id="s1", action_id="tool_k", idempotency_key="k1")
    )
    assert result.image_evidence == evidence
    assert result.agent_result_view is not None
    assert "b64" not in result.agent_result_view.payload
    assert result.agent_result_view.payload == {"note": "text-only"}


def test_module_has_no_domain_or_tooling_imports() -> None:
    source = Path(__file__).with_name("agent_result_view.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    banned_substrings = (
        "transcript_edit",
        "deed_to_ir",
    )

    def _has_banned_segment(module_name: str) -> bool:
        parts = [part for part in module_name.split(".") if part]
        return "domains" in parts or "tooling" in parts

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                assert not _has_banned_segment(name), name
                assert not any(s in name for s in banned_substrings), name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert not _has_banned_segment(module), module
            assert not any(s in module for s in banned_substrings), module
