"""Unit tests for the harness-native execution layer."""

from __future__ import annotations

from pathlib import Path

from harness.execution.contracts import (
    ExecutionSessionStartRequest,
    ExecutionState,
    ExecutionStepRequest,
)
from harness.execution.persistence import JsonFileExecutionPersistence
from harness.execution.session import ExecutionSessionManager


def test_start_session_seeds_initial_latest_refs() -> None:
    manager = ExecutionSessionManager()
    result = manager.start_session(
        ExecutionSessionStartRequest(
            run_id="run-1",
            session_id="session-1",
            initial_latest_refs={"seed": "artifact://seed"},
        )
    )
    assert result.session_id == "session-1"
    assert result.run_id == "run-1"
    assert result.dashboard.latest_refs.model_dump(mode="json") == {"seed": "artifact://seed"}


def test_step_idempotency_dedupes_second_execution() -> None:
    calls: list[str] = []
    manager = ExecutionSessionManager()
    manager.start_session(ExecutionSessionStartRequest(run_id="run-1", session_id="session-1"))
    manager.executor.register(
        "load_payload",
        lambda request: calls.append(request.action_id) or {
            "executed": True,
            "artifact_refs": ["artifact://draft-1"],
        },
    )

    first = manager.step(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="load_payload",
            idempotency_key="same-step",
        )
    )
    second = manager.step(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="load_payload",
            idempotency_key="same-step",
        )
    )

    assert first.execution_state == ExecutionState.EXECUTED
    assert second.execution_state == ExecutionState.DEDUPED
    assert calls == ["load_payload"]


def test_unregistered_action_refuses() -> None:
    manager = ExecutionSessionManager()
    manager.start_session(ExecutionSessionStartRequest(run_id="run-1", session_id="session-1"))

    result = manager.step(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="missing_action",
            idempotency_key="missing-step",
        )
    )

    assert result.execution_state == ExecutionState.REFUSED
    assert result.refusal is not None
    assert result.refusal.reason_code == "action_not_registered"


def test_json_file_persistence_round_trip(tmp_path: Path) -> None:
    persistence = JsonFileExecutionPersistence(tmp_path)
    manager = ExecutionSessionManager(persistence=persistence)
    manager.start_session(ExecutionSessionStartRequest(run_id="run-1", session_id="session-1"))
    manager.executor.register(
        "load_payload",
        lambda request: {
            "executed": True,
            "artifact_refs": ["artifact://draft-1"],
            "outputs": {"count": 1},
        },
    )

    result = manager.step(
        ExecutionStepRequest(
            session_id="session-1",
            action_id="load_payload",
            idempotency_key="step-1",
        )
    )

    assert result.execution_state == ExecutionState.EXECUTED
    run_path = tmp_path / "runs" / "run-1.json"
    session_path = tmp_path / "sessions" / "session-1.json"
    assert run_path.exists()
    assert session_path.exists()

    loaded_session = persistence.load_session(str(session_path))
    assert loaded_session.run_artifact.latest_refs == {"artifact://draft-1": "artifact://draft-1"}
    assert len(loaded_session.records) == 1
