from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import harness.cli.run_state as cli_run_state
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


def _seed_cli_run_state(tmp_path: Path, monkeypatch, run_id: str) -> None:
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    monkeypatch.setattr(cli_run_state, "cli_runs_root", lambda: tmp_path / "cli_runs")
    cli_run_state.write_state(
        cli_run_state.new_run_state(
            run_id=run_id,
            pid=4242,
            loop_kind="harness_cli",
            mode="stub",
            spawn_argv=["python", "-m", "harness.cli.stub_worker"],
            status="started",
        )
    )


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


def test_runner_invokes_orchestration_and_writes_loop_result_artifacts(tmp_path: Path, monkeypatch) -> None:
    tool_calls: list[ExecutionStepRequest] = []
    adapter = FakeSurfaceAdapter(calls=[], surface=_surface(tool_calls))
    model_calls: list[tuple[str, str]] = []
    run_id = "run-1"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
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
            "run_id": run_id,
            "session_id": "session-1",
            "request_id_prefix": "req-1",
            "max_iterations": 3,
        }
    )

    assert result.status == "completed"
    assert result.reason_code == "complete_run"
    assert result.result_payload["terminal_summary"] == "finished"
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
    assert "Plattera harness" in model_calls[0][0]
    assert "select_tool" in model_calls[0][0]
    assert len(tool_calls) == 1
    assert tool_calls[0].action_id == "select_tool"
    assert tool_calls[0].inputs == {"value": "alpha"}

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "completed"
    assert result_doc["reason_code"] == "complete_run"
    assert result_doc["terminal_class"] == "completed"
    assert result_doc["terminal_summary"] == "finished"
    assert result_doc["iterations"] == 2
    assert result_doc["latest_refs"] == {"artifact://selected": "artifact://selected"}
    assert done_doc["status"] == "completed"
    assert done_doc["reason_code"] == "complete_run"
    assert done_doc["terminal_class"] == "completed"
    assert done_doc["terminal_summary"] == "finished"
    assert done_doc["latest_refs"] == {"artifact://selected": "artifact://selected"}
    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.status == "completed"


def test_runner_writes_mechanical_failure_for_invalid_model_json(tmp_path: Path, monkeypatch) -> None:
    adapter = FakeSurfaceAdapter(
        calls=[],
        surface=TurnSurface(
            surface_id="surface-a",
            blocks=(TurnBlock(content="block-1", metadata={}),),
            payload={},
            tool_bindings=(),
        ),
    )
    run_id = "run-invalid-json"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        del prompt, model
        return "not valid json"

    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    with pytest.raises(RuntimeRunnerError) as exc_info:
        runner.run(launch_context={"model": "gpt-5.4-mini", "run_id": run_id})

    assert "invalid_model_action_json" in str(exc_info.value)
    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "failed"
    assert result_doc["reason_code"] == "invalid_model_action_json"
    assert result_doc["error"] == "model output was not valid JSON"
    assert done_doc["status"] == "failed"
    assert done_doc["reason_code"] == "invalid_model_action_json"
    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.status == "failed"


def test_runner_executes_transcript_edit_tool_and_writes_artifacts(tmp_path: Path, monkeypatch) -> None:
    dossier_root = tmp_path / "dossiers_data"
    dossier_root.mkdir()
    _write_transcript_edit_fixture(dossier_root)
    monkeypatch.setattr(config_paths, "dossiers_root", lambda: dossier_root)
    run_id = "practice-live-smoke-1"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    model_calls: list[tuple[str, str]] = []

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append((prompt, model))
        if len(model_calls) == 1:
            return json.dumps(
                {
                    "action_type": "hydrate_artifact_refs",
                    "action_inputs": {
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
            "run_id": run_id,
            "model": "gpt-o4-mini",
            "max_iterations": 2,
        }
    )

    assert result.status == "completed"
    assert result.reason_code == "complete_run"
    assert result.result_payload["terminal_summary"] == "finished"
    assert len(model_calls) == 2

    tool_events = [event for event in result.result_payload["trace_events"] if event.get("event_kind") == "tool_execution"]
    assert len(tool_events) == 1
    assert tool_events[0]["payload"]["action_type"] == "hydrate_artifact_refs"

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "completed"
    assert result_doc["reason_code"] == "complete_run"
    assert result_doc["terminal_summary"] == "finished"
    assert done_doc["status"] == "completed"
    assert done_doc["reason_code"] == "complete_run"
    assert done_doc["terminal_summary"] == "finished"
    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.status == "completed"


def test_audit_writer_finalize_called_even_when_loop_raises(tmp_path: Path, monkeypatch) -> None:
    """P1: audit artifacts must be written even if the orchestration loop raises."""
    import json as _json
    import os

    # Set HARNESS_CLI_RUN_ID so the audit writer targets a real directory.
    run_id = "audit-failure-test"
    cli_run_dir = tmp_path / "cli_runs" / run_id
    cli_run_dir.mkdir(parents=True)

    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    # Point cli_runs_root at tmp_path/cli_runs so run_dir() resolves correctly.
    import harness.cli.run_state as rs_mod
    monkeypatch.setattr(rs_mod, "cli_runs_root", lambda: tmp_path / "cli_runs")

    call_count = 0

    def exploding_caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        # First call records something in the audit buffer, then raises.
        if call_count == 1:
            return {"success": False, "error": "Connection error."}
        raise RuntimeError("loop exploded")

    tool_calls: list[ExecutionStepRequest] = []
    surface = _surface(tool_calls)
    adapter = FakeSurfaceAdapter(calls=[], surface=surface)

    runner = RuntimeRunner(
        adapter=adapter,
        model_caller=exploding_caller,
        targets=_targets(tmp_path),
    )

    with pytest.raises(Exception):
        runner.run(launch_context={"max_iterations": 2, "run_id": run_id})

    # The audit dir should exist and have at least the index.json written.
    audit_dir = cli_run_dir / "audit"
    assert audit_dir.exists(), "audit dir must be created even on failed run"
    assert (audit_dir / "index.json").exists(), "index.json must be written even on failed run"
    index = _json.loads((audit_dir / "index.json").read_text())
    assert index["terminal_class"] == "failed"

    # Turn file for the connection-error turn should also be present.
    turn_files = list(audit_dir.glob("turn_*.json"))
    assert len(turn_files) >= 1, "at least one turn must be recorded before the failure"


def test_default_model_caller_passes_through_call_options(monkeypatch) -> None:
    """The runner default caller is a plain pass-through; output policy is set by the call site."""
    from services.llm.call_options import LlmCallOptions

    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeOpenAIService:
        def call_text(self, prompt: str, model: str, **kwargs):
            calls.append((prompt, model, dict(kwargs)))
            return {"success": True, "text": '{"action_type": null}'}

    monkeypatch.setattr(runner_module, "OpenAIService", FakeOpenAIService)

    model_caller = runner_module._build_default_model_caller(model_name="gpt-5.4-mini")
    opts = LlmCallOptions(output_mode="json_object", phase="choose_action")

    result = model_caller("prompt text", "", call_options=opts)

    assert result == {"success": True, "text": '{"action_type": null}'}
    assert len(calls) == 1
    prompt_sent, model_sent, kwargs_sent = calls[0]
    assert prompt_sent == "prompt text"
    assert model_sent == "gpt-5.4-mini"
    # call_options is passed through; no json_mode kwarg injected by the runner
    assert "json_mode" not in kwargs_sent
    assert kwargs_sent.get("call_options") is opts
