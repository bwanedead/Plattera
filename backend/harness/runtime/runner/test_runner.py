from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from domains.mapping.transcript_edit.runtime_adapter import build_transcript_edit_runtime_adapter
import config.paths as config_paths
from harness.execution.contracts import ActionDispatchResult, ExecutionStepRequest
from harness.runtime.composition import ToolBinding, TurnBlock, TurnSurface
from harness.runtime.runner import RuntimeArtifactTargets, RuntimeRunner, RuntimeRunnerError
from harness.runtime.runner import runner as runner_module


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


def _write_transcript_edit_fixture(root: Path) -> None:
    dossier_id = "9f5eecb6-cd7e-483c-b691-b76aa7132e8e"
    transcription_id = "draft_legal_text_image"
    run_dir = root / "views" / "transcriptions" / dossier_id / transcription_id
    raw_dir = run_dir / "raw"
    te_dir = run_dir / "transcript_edit"
    assoc_dir = root / "associations"

    raw_dir.mkdir(parents=True, exist_ok=True)
    te_dir.mkdir(parents=True, exist_ok=True)
    assoc_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / "run.json").write_text(
        json.dumps({"completed_drafts": ["peer_alpha"]}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (raw_dir / "peer_alpha.json").write_text(
        json.dumps(
            {
                "sections": [
                    {
                        "body": "Peer alpha text for deterministic hydrate testing.",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (te_dir / "working.json").write_text(json.dumps({"status": "draft"}, ensure_ascii=False, indent=2), encoding="utf-8")
    (assoc_dir / f"assoc_{dossier_id}.json").write_text(
        json.dumps(
            {
                "associations": [
                    {
                        "transcription_id": transcription_id,
                        "metadata": {},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
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
                    "state_patch": None,
                    "continuity_journal_entry": {"runner_stub": True},
                    "operator_progress_message": None,
                }
            )
        return json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "plan-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "finished",
                "state_patch": None,
                "continuity_journal_entry": {"runner_stub": True},
                "operator_progress_message": None,
            }
        )

    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "model": "gpt-5.4-mini",
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
            "model": "gpt-5.4-mini",
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
        runner.run(launch_context={"model": "gpt-5.4-mini"})

    assert "invalid_model_action_json" in str(exc_info.value)
    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "failed"
    assert result_doc["reason_code"] == "invalid_model_action_json"
    assert result_doc["error"] == "model output was not valid JSON"
    assert done_doc["status"] == "failed"
    assert done_doc["reason_code"] == "invalid_model_action_json"


def test_runner_executes_transcript_edit_tool_and_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    dossier_root = tmp_path / "dossiers_data"
    dossier_root.mkdir()
    _write_transcript_edit_fixture(dossier_root)
    monkeypatch.setattr(config_paths, "dossiers_root", lambda: dossier_root)

    model_calls: list[tuple[str, str]] = []

    def model_caller(prompt: str, model: str) -> str:
        model_calls.append((prompt, model))
        if len(model_calls) == 1:
            return json.dumps(
                {
                    "action_type": "hydrate_t0_draft_refs",
                    "action_inputs": {
                        "dossier_id": "9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
                        "transcription_id": "draft_legal_text_image",
                        "ref_ids": ["t0:raw:peer_alpha"],
                    },
                    "idempotency_key": "ik-1",
                    "skip_execution": False,
                    "wait_for_human": False,
                    "complete_run": False,
                    "rationale": "hydrate the requested draft refs",
                    "state_patch": None,
                    "continuity_journal_entry": {"runner_stub": True},
                    "operator_progress_message": None,
                }
            )
        return json.dumps(
            {
                "action_type": "noop",
                "action_inputs": {},
                "idempotency_key": "ik-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "finished",
                "state_patch": None,
                "continuity_journal_entry": {"runner_stub": True},
                "operator_progress_message": None,
            }
        )

    runner = RuntimeRunner(
        adapter=build_transcript_edit_runtime_adapter(),
        model_caller=model_caller,
        targets=_targets(tmp_path),
    )

    result = runner.run(
        launch_context={
            "dossier_id": "9f5eecb6-cd7e-483c-b691-b76aa7132e8e",
            "transcription_id": "draft_legal_text_image",
            "run_id": "practice-live-smoke-1",
            "model": "gpt-o4-mini",
            "max_iterations": 2,
        }
    )

    assert result.status == "completed"
    assert result.reason_code == "finished"
    assert len(model_calls) == 2

    tool_events = [event for event in result.result_payload["trace_events"] if event.get("event_kind") == "tool_execution"]
    assert len(tool_events) == 1
    assert tool_events[0]["payload"]["action_type"] == "hydrate_t0_draft_refs"

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "completed"
    assert result_doc["reason_code"] == "finished"
    assert done_doc["status"] == "completed"
    assert done_doc["reason_code"] == "finished"


def test_default_model_caller_requests_relaxed_json_mode(monkeypatch) -> None:
    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeOpenAIService:
        def call_text(self, prompt: str, model: str, **kwargs):
            calls.append((prompt, model, dict(kwargs)))
            return {"success": True, "text": '{"action_type": null}'}

    monkeypatch.setattr(runner_module, "OpenAIService", FakeOpenAIService)

    model_caller = runner_module._build_default_model_caller(model_name="gpt-5.4-mini")

    result = model_caller("prompt text", "")

    assert result == {"success": True, "text": '{"action_type": null}'}
    assert calls == [("prompt text", "gpt-5.4-mini", {"json_mode": "relaxed"})]
