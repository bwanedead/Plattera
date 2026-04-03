from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness.execution.contracts import ActionDispatchResult, ExecutionStepRequest
from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from harness.runtime.runner import RuntimeArtifactTargets, RuntimeRunner, RuntimeRunnerError


@dataclass
class FakeSurfaceAdapter:
    calls: list[dict[str, object]]
    surface: TurnSurface

    def build_turn_surface(self, launch_context: dict[str, object]) -> TurnSurface:
        self.calls.append(dict(launch_context))
        return self.surface


def _targets(tmp_path: Path) -> RuntimeArtifactTargets:
    return RuntimeArtifactTargets(done_file=tmp_path / "done.json", result_file=tmp_path / "result.json")


def _surface(tool_calls: list[ExecutionStepRequest]) -> TurnSurface:
    def _handler(request: ExecutionStepRequest) -> ActionDispatchResult:
        tool_calls.append(request)
        return ActionDispatchResult(
            action_id=request.action_id,
            executed=True,
            outputs={"selected": True},
            artifact_refs=("artifact://selected",),
            idempotency_key=request.idempotency_key,
        )

    return TurnSurface(
        surface_id="surface-a",
        blocks=(TurnBlock(content="block-1", metadata={"kind": "prompt"}),),
        payload={"opaque": {"scope": "generic"}},
        tool_bindings=(ToolBinding(tool_id="select_tool", handler=_handler),),
    )


def test_runner_invokes_orchestration_and_writes_loop_result_artifacts(tmp_path: Path) -> None:
    tool_calls: list[ExecutionStepRequest] = []
    adapter = FakeSurfaceAdapter(calls=[], surface=_surface(tool_calls))
    model_calls: list[tuple[str, str]] = []

    def model_caller(prompt: str, model: str) -> str:
        model_calls.append((prompt, model))
        if len(model_calls) == 1:
            return json.dumps(
                {
                    "action_type": "select_tool",
                    "action_inputs": {"value": "alpha"},
                    "idempotency_key": "plan-1",
                    "skip_execution": False,
                    "wait_for_human": False,
                    "complete_run": False,
                    "rationale": "execute tool",
                }
            )
        return json.dumps(
            {
                "action_inputs": {},
                "idempotency_key": "plan-2",
                "skip_execution": False,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "finished",
            }
        )

    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "model": "gpt-5.2",
            "run_id": "run-1",
            "session_id": "session-1",
            "request_id_prefix": "req-1",
            "max_iterations": 3,
        }
    )

    assert result.status == "completed"
    assert result.reason_code == "finished"
    assert adapter.calls == [
        {
            "max_iterations": 3,
            "model": "gpt-5.2",
            "request_id_prefix": "req-1",
            "run_id": "run-1",
            "session_id": "session-1",
        }
    ]
    assert len(model_calls) == 2
    assert "select_tool" in model_calls[0][0]
    assert len(tool_calls) == 1
    assert tool_calls[0].action_id == "select_tool"
    assert tool_calls[0].inputs == {"value": "alpha"}

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "completed"
    assert result_doc["reason_code"] == "finished"
    assert result_doc["terminal_class"] == "completed"
    assert result_doc["iterations"] == 2
    assert result_doc["latest_refs"] == {"artifact://selected": "artifact://selected"}
    assert done_doc["status"] == "completed"
    assert done_doc["reason_code"] == "finished"
    assert done_doc["terminal_class"] == "completed"
    assert done_doc["latest_refs"] == {"artifact://selected": "artifact://selected"}


def test_runner_writes_mechanical_failure_for_invalid_model_json(tmp_path: Path) -> None:
    adapter = FakeSurfaceAdapter(
        calls=[],
        surface=TurnSurface(
            surface_id="surface-a",
            blocks=(TurnBlock(content="block-1", metadata={}),),
            payload={},
            tool_bindings=(),
        ),
    )

    def model_caller(prompt: str, model: str) -> str:
        del prompt, model
        return "not valid json"

    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    with pytest.raises(RuntimeRunnerError) as exc_info:
        runner.run(launch_context={"model": "gpt-5.2"})

    assert "invalid_model_action_json" in str(exc_info.value)
    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "failed"
    assert result_doc["reason_code"] == "invalid_model_action_json"
    assert result_doc["error"] == "model output was not valid JSON"
    assert done_doc["status"] == "failed"
    assert done_doc["reason_code"] == "invalid_model_action_json"

