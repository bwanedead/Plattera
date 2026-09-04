from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from types import SimpleNamespace

import pytest

import harness.cli.run_state as cli_run_state
from domains import ClosureDimensionStandard, DomainClosurePolicy
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


@dataclass
class FakePolicyManifest:
    domain_id: str
    closure_policy: DomainClosurePolicy


@dataclass
class FakePolicyAdapter(FakeSurfaceAdapter):
    manifest: FakePolicyManifest


def _targets(tmp_path: Path) -> RuntimeArtifactTargets:
    return RuntimeArtifactTargets(done_file=tmp_path / "done.json", result_file=tmp_path / "result.json")


def _seed_cli_run_state(tmp_path: Path, monkeypatch, run_id: str) -> None:
    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: tmp_path / "cli_runs")
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
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "plan-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "finished",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
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
            "workspace_id": "run-1",
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

    result = runner.run(launch_context={"model": "gpt-5.4-mini", "run_id": run_id})

    assert result.status == "failed"
    assert result.reason_code == "recoverable_turn_failure_budget_exhausted"
    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "failed"
    assert result_doc["reason_code"] == "recoverable_turn_failure_budget_exhausted"
    assert done_doc["status"] == "failed"
    assert done_doc["reason_code"] == "recoverable_turn_failure_budget_exhausted"
    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.status == "failed"


def test_runner_model_call_failed_agrees_across_terminal_artifacts(
    tmp_path: Path, monkeypatch
) -> None:
    """Production-shaped provider failure after turn 1 must agree on failed/model_call_failed."""
    adapter = FakeSurfaceAdapter(
        calls=[],
        surface=TurnSurface(
            surface_id="surface-a",
            blocks=(TurnBlock(content="block-1", metadata={}),),
            payload={},
            tool_bindings=(),
        ),
    )
    run_id = "run-model-call-failed"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> dict[str, Any]:
        del prompt, model
        return {
            "success": False,
            "error": "streaming is not supported for this model",
            "text": None,
        }

    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    with pytest.raises(RuntimeRunnerError) as exc_info:
        runner.run(launch_context={"model": "gpt-5.4-mini", "run_id": run_id, "max_iterations": 2})

    assert exc_info.value.reason_code == "model_call_failed"
    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "failed"
    assert result_doc["reason_code"] == "model_call_failed"
    assert done_doc["status"] == "failed"
    assert done_doc["reason_code"] == "model_call_failed"

    audit_dir = cli_run_state.run_dir(run_id) / "audit"
    idx = json.loads((audit_dir / "index.json").read_text(encoding="utf-8"))
    review = (audit_dir / "review.md").read_text(encoding="utf-8")
    timeline = (audit_dir / "human" / "timeline.md").read_text(encoding="utf-8")
    assert idx["terminal_class"] == "failed"
    assert idx["reason_code"] == "model_call_failed"
    assert idx["iterations"] == 1
    assert "**Terminal:** `failed`" in review
    assert "**Reason:** `model_call_failed`" in review
    assert "**Iterations:** 1" in review
    assert "- terminal_class: failed" in timeline
    assert "- reason_code: model_call_failed" in timeline
    assert "- iterations: 1" in timeline
    assert "Run-Level Terminal Override" not in timeline
    assert "Run-Level Terminal Override" not in review
    assert (audit_dir / "turn_0001.json").is_file()
    assert result_doc["reason_code"] != "runner_exception"
    assert idx["reason_code"] != "runner_exception"


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
                "action_type": None,
                "idempotency_key": "ik-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "finished",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
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
            # Smoke test targets hydrate execution, not hard closure enforcement.
            "domain_closure_policy": {"hard_enforced": False},
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


def test_audit_writer_finalize_called_on_resumable_model_interruption(tmp_path: Path, monkeypatch) -> None:
    """Audit artifacts must be written when a resumable model interruption pauses the run."""
    import json as _json
    import os

    # Set HARNESS_CLI_RUN_ID so the audit writer targets a real directory.
    run_id = "audit-failure-test"
    cli_run_dir = tmp_path / "cli_runs" / run_id
    cli_run_dir.mkdir(parents=True)
    (cli_run_dir / "state.json").write_text(
        _json.dumps({"run_id": run_id}),
        encoding="utf-8",
    )

    monkeypatch.setenv("HARNESS_CLI_RUN_ID", run_id)
    import harness.cli.run_layout as layout_mod
    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: tmp_path / "cli_runs")

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

    result = runner.run(launch_context={"max_iterations": 2, "run_id": run_id})
    assert result.status == "paused"
    assert result.reason_code == "model_connection_interrupted"
    assert bool(result.result_payload.get("resumable"))

    # The audit dir should exist and have at least the index.json written.
    audit_dir = cli_run_dir / "audit"
    assert audit_dir.exists(), "audit dir must be created even on failed run"
    assert (audit_dir / "index.json").exists(), "index.json must be written even on failed run"
    index = _json.loads((audit_dir / "index.json").read_text())
    assert index["terminal_class"] == "paused"
    assert index["reason_code"] == "model_connection_interrupted"

    # Turn file for the connection-error turn should also be present.
    turn_files = list(audit_dir.glob("turn_*.json"))
    assert len(turn_files) >= 1, "at least one turn must be recorded before the failure"


def test_default_model_caller_passes_through_call_options(monkeypatch) -> None:
    """The runner default caller is a plain pass-through; output policy is set by the call site."""
    from services.llm.base import LLMService
    from services.llm.call_options import LlmCallOptions
    from services.registry import ServiceRegistry, reset_registry_for_tests

    reset_registry_for_tests()
    calls: list[tuple[str, str, dict[str, object]]] = []

    class FakeOpenAIService(LLMService):
        name = "openai"
        models = {"gpt-5.4-mini": {"context_window_tokens": 400_000}}

        def is_available(self) -> bool:
            return True

        def call_text(self, prompt: str, model: str, **kwargs):
            calls.append((prompt, model, dict(kwargs)))
            return {"success": True, "text": '{"action_type": null}'}

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            return self.call_text(prompt, model, **kwargs)

    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(FakeOpenAIService())
    monkeypatch.setattr("services.registry._registry", reg)
    monkeypatch.setattr(
        "harness.runtime.llm.provider_model_caller.get_registry",
        lambda: reg,
    )

    try:
        model_caller = runner_module._build_default_model_caller(model_name="gpt-5.4-mini")
        opts = LlmCallOptions(output_mode="json_object", phase="choose_action")

        result = model_caller("prompt text", "", call_options=opts)

        assert isinstance(result, dict)
        assert result.get("success") is True
        assert result.get("text") == '{"action_type": null}'
        trace = result.get("llm_call_trace")
        assert isinstance(trace, dict)
        assert trace.get("call_role") == "parent"
        assert trace.get("call_name") == "choose_action"
        assert trace.get("provider") == "openai"
        assert trace.get("prompt_char_count") == len("prompt text")
        assert len(calls) == 1
        prompt_sent, model_sent, kwargs_sent = calls[0]
        assert prompt_sent == "prompt text"
        assert model_sent == "gpt-5.4-mini"
        # call_options is passed through; no json_mode kwarg injected by the runner
        assert "json_mode" not in kwargs_sent
        assert kwargs_sent.get("call_options") is opts
    finally:
        reset_registry_for_tests()


def test_default_model_caller_downgrades_streaming_when_provider_cannot_stream(monkeypatch) -> None:
    """Run-context streaming request must not fail a non-streaming provider."""
    from services.llm.base import LLMService
    from services.registry import ServiceRegistry, reset_registry_for_tests

    from harness.runtime.llm.llm_call_trace import extract_streaming_requested
    from harness.runtime.llm.streaming_config import apply_streaming_to_call_options
    from services.llm.call_options import LlmCallOptions

    reset_registry_for_tests()
    received: list[dict[str, object]] = []

    class StrictNonStreaming(LLMService):
        name = "meta"
        models = {"muse-spark-1.2-contributor": {"context_window_tokens": 1_048_576}}

        def is_available(self) -> bool:
            return True

        def supports_streaming(self) -> bool:
            return False

        def call_text(self, prompt: str, model: str, **kwargs):
            streaming = extract_streaming_requested(
                kwargs=kwargs,
                call_options=kwargs.get("call_options"),
            )
            received.append({"streaming": streaming, "call_options": kwargs.get("call_options")})
            if streaming:
                return {
                    "success": False,
                    "error": "streaming_unsupported",
                    "finish_reason": "streaming_unsupported",
                    "text": None,
                    "model": model,
                }
            return {"success": True, "text": '{"ok":true}', "model": model}

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            return self.call_text(prompt, model, **kwargs)

    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(StrictNonStreaming())
    monkeypatch.setattr("services.registry._registry", reg)
    monkeypatch.setattr(
        "harness.runtime.llm.provider_model_caller.get_registry",
        lambda: reg,
    )
    try:
        caller = runner_module._build_default_model_caller(
            model_name="muse-spark-1.2-contributor"
        )
        original = LlmCallOptions(output_mode="json_object", phase="choose_action")
        opts = apply_streaming_to_call_options(
            original,
            run_context={"llm_streaming": True},
        )
        assert opts.streaming is True
        result = caller("prompt text", "muse-spark-1.2-contributor", call_options=opts)
        assert result["success"] is True
        assert result["text"] == '{"ok":true}'
        assert received[0]["streaming"] is False
        assert opts.streaming is True
        trace = result["llm_call_trace"]
        assert trace["streaming_requested"] is True
        assert trace["streaming_supported"] is False
        assert trace["streaming_effective"] is False
        assert trace["provider"] == "meta"
    finally:
        reset_registry_for_tests()


def test_default_model_caller_does_not_construct_openai_service_directly(monkeypatch) -> None:
    from services.llm.base import LLMService
    from services.registry import ServiceRegistry, reset_registry_for_tests

    reset_registry_for_tests()

    class BoomOpenAI:
        def __init__(self, *args, **kwargs):
            raise AssertionError("runner must not construct OpenAIService directly")

    monkeypatch.setattr("services.llm.openai.OpenAIService", BoomOpenAI)

    class FakeService(LLMService):
        name = "openai"
        models = {"gpt-5.4-mini": {"context_window_tokens": 400_000}}

        def is_available(self) -> bool:
            return True

        def call_text(self, prompt: str, model: str, **kwargs):
            return {"success": True, "text": "{}"}

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            return self.call_text(prompt, model, **kwargs)

    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(FakeService())
    monkeypatch.setattr("services.registry._registry", reg)
    monkeypatch.setattr(
        "harness.runtime.llm.provider_model_caller.get_registry",
        lambda: reg,
    )
    try:
        caller = runner_module._build_default_model_caller(model_name="gpt-5.4-mini")
        assert caller("hi", "gpt-5.4-mini")["success"] is True
    finally:
        reset_registry_for_tests()


def test_default_model_caller_fails_before_loop_when_provider_unavailable(monkeypatch) -> None:
    from services.llm.base import LLMService
    from services.registry import ModelProviderError, ServiceRegistry, reset_registry_for_tests

    reset_registry_for_tests()

    class Unavailable(LLMService):
        name = "openai"
        models = {"gpt-5.6-luna": {"context_window_tokens": 400_000}}

        def is_available(self) -> bool:
            return False

        def call_text(self, prompt: str, model: str, **kwargs):
            raise AssertionError("must not call")

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            raise AssertionError("must not call")

    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(Unavailable())
    monkeypatch.setattr("services.registry._registry", reg)
    monkeypatch.setattr(
        "harness.runtime.llm.provider_model_caller.get_registry",
        lambda: reg,
    )
    try:
        with pytest.raises(ModelProviderError) as raised:
            runner_module._build_default_model_caller(model_name="gpt-5.6-luna")
        assert raised.value.reason_code == "model_provider_unavailable"
    finally:
        reset_registry_for_tests()


@pytest.mark.parametrize(
    ("scenario", "model_id", "reason_code"),
    [
        ("unavailable", "known-unavailable-model", "model_provider_unavailable"),
        ("unknown", "totally-unknown-model", "model_provider_not_found"),
        ("ambiguous", "shared-model", "model_provider_ambiguous"),
    ],
)
def test_runner_fails_before_model_loop_for_provider_resolution_errors(
    tmp_path: Path,
    monkeypatch,
    scenario: str,
    model_id: str,
    reason_code: str,
) -> None:
    """Production-shaped runner boundary: provider readiness fails before the kernel loop."""
    from services.llm.base import LLMService
    from services.registry import ServiceRegistry, reset_registry_for_tests

    reset_registry_for_tests()
    call_log: list[tuple[str, str]] = []
    kernel_calls: list[str] = []

    class _Fake(LLMService):
        def __init__(self, *, name: str, models: dict[str, dict], available: bool) -> None:
            self.name = name
            self.models = models
            self._available = available

        def is_available(self) -> bool:
            return self._available

        def call_text(self, prompt: str, model: str, **kwargs):
            call_log.append((self.name, model))
            raise AssertionError("model call must not occur")

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            return self.call_text(prompt, model, **kwargs)

    reg = ServiceRegistry(discover=False)
    if scenario == "unavailable":
        reg.accept_llm_service(
            _Fake(
                name="alpha",
                models={model_id: {"context_window_tokens": 10_000}},
                available=False,
            )
        )
    elif scenario == "ambiguous":
        reg.accept_llm_service(
            _Fake(name="alpha", models={model_id: {"context_window_tokens": 1}}, available=True)
        )
        reg.accept_llm_service(
            _Fake(name="beta", models={model_id: {"context_window_tokens": 2}}, available=True)
        )
    # unknown: leave registry empty of the requested model

    monkeypatch.setattr("services.registry._registry", reg)
    monkeypatch.setattr(
        "harness.runtime.llm.provider_model_caller.get_registry",
        lambda: reg,
    )

    def _kernel_must_not_run(**kwargs: Any) -> Any:
        del kwargs
        kernel_calls.append("entered")
        raise AssertionError("orchestration kernel must not run")

    monkeypatch.setattr(runner_module, "run_orchestration_kernel_loop", _kernel_must_not_run)

    adapter = FakeSurfaceAdapter(
        calls=[],
        surface=TurnSurface(
            surface_id="surface-a",
            blocks=(TurnBlock(content="block-1", metadata={}),),
            payload={},
            tool_bindings=(),
        ),
    )
    run_id = f"run-provider-{scenario}"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)
    # No injected model_caller — use the production default path.
    runner = RuntimeRunner(adapter=adapter, targets=_targets(tmp_path))

    try:
        with pytest.raises(RuntimeRunnerError) as exc_info:
            runner.run(launch_context={"model": model_id, "run_id": run_id, "max_iterations": 1})
        assert reason_code in str(exc_info.value)
        assert exc_info.value.reason_code == reason_code
        assert call_log == []
        assert kernel_calls == []
        result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
        done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
        assert result_doc["status"] == "failed"
        assert result_doc["reason_code"] == reason_code
        assert done_doc["status"] == "failed"
        assert done_doc["reason_code"] == reason_code
        assert result_doc["reason_code"] != "runner_exception"
        assert result_doc["reason_code"] != "invalid_model_action_json"
    finally:
        reset_registry_for_tests()


def test_runner_missing_meta_key_fails_before_kernel_as_provider_unavailable(
    tmp_path: Path, monkeypatch
) -> None:
    """Default Muse path must fail closed before the kernel when Meta is unconfigured."""
    from services.llm.base import LLMService
    from services.registry import ServiceRegistry, reset_registry_for_tests

    reset_registry_for_tests()
    muse_models = {
        "muse-spark-1.2-contributor": {"context_window_tokens": 1_048_576},
        "muse-spark-1.3-contributor": {"context_window_tokens": 1_048_576},
    }
    kernel_calls: list[str] = []

    class UnavailableMeta(LLMService):
        name = "meta"
        models = muse_models

        def is_available(self) -> bool:
            return False

        def call_text(self, prompt: str, model: str, **kwargs):
            raise AssertionError("must not call")

        def call_vision(self, prompt: str, image_data: str, model: str, **kwargs):
            raise AssertionError("must not call")

    reg = ServiceRegistry(discover=False)
    reg.accept_llm_service(UnavailableMeta())
    monkeypatch.setattr("services.registry._registry", reg)
    monkeypatch.setattr(
        "harness.runtime.llm.provider_model_caller.get_registry",
        lambda: reg,
    )
    monkeypatch.delenv("HARNESS_CLI_MODEL", raising=False)

    def _kernel_must_not_run(**kwargs: Any) -> Any:
        del kwargs
        kernel_calls.append("entered")
        raise AssertionError("orchestration kernel must not run")

    monkeypatch.setattr(runner_module, "run_orchestration_kernel_loop", _kernel_must_not_run)
    adapter = FakeSurfaceAdapter(
        calls=[],
        surface=TurnSurface(
            surface_id="surface-a",
            blocks=(TurnBlock(content="block-1", metadata={}),),
            payload={},
            tool_bindings=(),
        ),
    )
    run_id = "run-muse-unavailable"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)
    runner = RuntimeRunner(adapter=adapter, targets=_targets(tmp_path))
    try:
        with pytest.raises(RuntimeRunnerError) as exc_info:
            # Omit model so DEFAULT_HARNESS_MODEL (Muse) is selected.
            runner.run(launch_context={"run_id": run_id, "max_iterations": 1})
        assert exc_info.value.reason_code == "model_provider_unavailable"
        assert kernel_calls == []
        result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
        assert result_doc["reason_code"] == "model_provider_unavailable"
        assert result_doc["reason_code"] != "invalid_model_action_json"
    finally:
        reset_registry_for_tests()


def test_select_model_name_prefers_launch_context_over_cli_env(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_CLI_MODEL", "gpt-5.4-mini")
    assert runner_module._select_model_name({"model": "gpt-5.4"}) == "gpt-5.4"


def test_select_model_name_falls_back_to_cli_env(monkeypatch) -> None:
    monkeypatch.setenv("HARNESS_CLI_MODEL", "gpt-5.4-mini")
    assert runner_module._select_model_name({}) == "gpt-5.4-mini"


def test_select_model_name_strips_candidates_before_precedence(monkeypatch) -> None:
    """Whitespace-only launch model must not suppress a usable CLI override."""
    monkeypatch.setenv("HARNESS_CLI_MODEL", "gpt-5.6-terra")
    assert runner_module._select_model_name({"model": "   "}) == "gpt-5.6-terra"

    monkeypatch.delenv("HARNESS_CLI_MODEL", raising=False)
    assert runner_module._select_model_name({"model": "   "}) == "muse-spark-1.3-contributor"

    monkeypatch.setenv("HARNESS_CLI_MODEL", "   ")
    assert runner_module._select_model_name({"model": "   "}) == "muse-spark-1.3-contributor"

    monkeypatch.setenv("HARNESS_CLI_MODEL", "gpt-5.6-terra")
    assert runner_module._select_model_name({"model": "gpt-5.4-mini"}) == "gpt-5.4-mini"


def test_runner_injects_domain_closure_policy_into_orchestration_context(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}
    policy = DomainClosurePolicy(
        hard_enforced=True,
        enforce_on_complete=True,
        save_action_ids=("save_workspace_artifact",),
        publish_action_ids=("publish_workspace_artifact",),
        required_dimension_ids=("layer_a",),
        standards=(
            ClosureDimensionStandard(
                dimension_id="layer_a",
                title="Layer A",
                question="Is layer A closed?",
            ),
        ),
    )
    adapter = FakePolicyAdapter(
        calls=[],
        surface=TurnSurface(surface_id="surface-a", blocks=(), payload={}, tool_bindings=()),
        manifest=FakePolicyManifest(domain_id="fake_domain", closure_policy=policy),
    )

    def fake_loop(**kwargs: Any) -> Any:
        captured.update(kwargs["opaque_run_context"])
        return SimpleNamespace(
            terminal_class="completed",
            reason_code="complete_run",
            terminal_summary="done",
            iterations=1,
            session_id="sess",
            run_artifact_ref=None,
            latest_refs={},
            runtime_state={},
            trace_events=[],
            kernel_resume_snapshot=None,
        )

    monkeypatch.setattr(runner_module, "run_orchestration_kernel_loop", fake_loop)

    runner = RuntimeRunner(adapter=adapter, model_caller=lambda *args, **kwargs: "", targets=_targets(tmp_path))
    result = runner.run(launch_context={"run_id": "r1", "session_id": "s1", "request_id_prefix": "req1"})

    assert result.status == "completed"
    assert captured["domain_id"] == "fake_domain"
    assert captured["domain_closure_policy"]["hard_enforced"] is True
    assert captured["domain_closure_policy"]["save_action_ids"] == ["save_workspace_artifact"]
    assert captured["domain_closure_policy"]["publish_action_ids"] == ["publish_workspace_artifact"]
    assert captured["domain_closure_policy"]["required_dimension_ids"] == ["layer_a"]


def test_runner_injects_transcript_edit_action_batch_policy(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}
    adapter = build_transcript_edit_runtime_adapter()

    def fake_loop(**kwargs: Any) -> Any:
        captured.update(kwargs["opaque_run_context"])
        return SimpleNamespace(
            terminal_class="completed",
            reason_code="complete_run",
            terminal_summary="done",
            iterations=1,
            session_id="sess",
            run_artifact_ref=None,
            latest_refs={},
            runtime_state={},
            trace_events=[],
            kernel_resume_snapshot=None,
        )

    monkeypatch.setattr(runner_module, "run_orchestration_kernel_loop", fake_loop)
    monkeypatch.setattr(runner_module, "_build_audit_writer", lambda **kwargs: SimpleNamespace(finalize=lambda **kw: None))
    monkeypatch.setattr(runner_module, "_build_resume_checkpoint_writer", lambda: None)
    monkeypatch.setattr(runner_module, "_build_run_control_reader", lambda: None)

    runner = RuntimeRunner(adapter=adapter, model_caller=lambda *args, **kwargs: "", targets=_targets(tmp_path))
    runner.run(
        launch_context={
            "run_id": "r-te",
            "session_id": "s-te",
            "request_id_prefix": "req-te",
            "dossier_id": "d1",
            "transcription_id": "t1",
        }
    )

    policy = captured.get("action_batch_policy")
    assert isinstance(policy, dict)
    assert policy.get("max_batch_size") == 15
    assert policy["tool_caps"]["delegate_subtask"] == 15
    reminder = captured.get("delegate_observation_worklist_reminder")
    assert isinstance(reminder, str)
    assert "opportunistically harvest" in reminder


@pytest.mark.parametrize(
    ("terminal_class", "reason_code", "command"),
    [
        ("paused", "paused_by_operator", "pause"),
        ("stopped", "stopped_by_operator", "stop"),
    ],
)
def test_runner_writes_resumable_done_and_result_for_operator_interruption(
    tmp_path: Path,
    monkeypatch,
    terminal_class: str,
    reason_code: str,
    command: str,
) -> None:
    run_id = f"run-{terminal_class}"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)
    control_request = {
        "schema_version": 1,
        "request_id": f"req-{terminal_class}",
        "command": command,
        "requested_at_epoch_seconds": 1.0,
        "reason": "operator requested",
        "requested_by": "cli",
    }

    def fake_loop(**_kwargs: Any) -> Any:
        return SimpleNamespace(
            terminal_class=terminal_class,
            reason_code=reason_code,
            terminal_summary="operator requested",
            iterations=2,
            session_id="sess-control",
            run_artifact_ref=None,
            latest_refs={},
            runtime_state={
                "control_request": control_request,
                "resumable": True,
                "interrupted_at_iteration": 2,
            },
            trace_events=[],
            kernel_resume_snapshot={"schema_version": "kernel_resume.v1", "next_iteration": 3},
        )

    monkeypatch.setattr(runner_module, "run_orchestration_kernel_loop", fake_loop)

    runner = RuntimeRunner(
        adapter=FakeSurfaceAdapter(calls=[], surface=TurnSurface(surface_id="surface-a", blocks=(), payload={}, tool_bindings=())),
        model_caller=lambda *args, **kwargs: "",
        targets=_targets(tmp_path),
    )

    result = runner.run(launch_context={"run_id": run_id, "session_id": "sess-control", "request_id_prefix": "req-control"})

    assert result.status == terminal_class
    assert result.reason_code == reason_code

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))

    for payload in (result_doc, done_doc):
        assert payload["status"] == terminal_class
        assert payload["terminal_class"] == terminal_class
        assert payload["reason_code"] == reason_code
        assert payload["resumable"] is True
        assert payload["interrupted_at_iteration"] == 2
        assert payload["control_request"]["command"] == command


# ── HITL lifecycle tests ───────────────────────────────────────────────────────


def _blocking_hitl_model_caller() -> tuple[list[str], Any]:
    """Return (model_calls list, model_caller) where turn 1 emits blocking HITL, turn 2 completes."""
    model_calls: list[str] = []

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append(prompt)
        if len(model_calls) == 1:
            return json.dumps(
                {
                    "action_type": None,
                    "action_inputs": {},
                    "idempotency_key": "ik-hitl-1",
                    "skip_execution": True,
                    "wait_for_human": True,
                    "complete_run": False,
                    "rationale": "need human input",
                    "state_patch": None,
                    "continuity_journal_entry": {"stub": True},
                    "operator_progress_message": None,
                    "hitl_request": {
                        "prompt_id": "prompt-range-conflict",
                        "message": "Which range: 74 or 75?",
                        "choices": ["74", "75"],
                    },
                }
            )
        # Turn 2 — resumed after human answered.
        return json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-hitl-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "human answered, proceeding",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
            }
        )

    return model_calls, model_caller


def test_blocking_hitl_auto_resumes_when_answer_arrives(tmp_path: Path, monkeypatch) -> None:
    """Blocking HITL: run pauses, polls for feedback, auto-resumes, completes.

    Verifies:
    - status is completed (not waiting_human) when feedback arrives
    - done.json reflects the final completed status
    - two model turns occurred (one before pause, one after resume)
    - no manual restart was needed
    """
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths

    run_id = "run-hitl-auto-resume"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    # Feedback store: answer is ready immediately for the blocking prompt.
    answer_entry = {"prompt_id": "prompt-range-conflict", "choice": "74", "submitted_at_epoch_seconds": 1}
    monkeypatch.setattr(fb_mod, "list_entries", lambda **_kw: [answer_entry])
    # Route sidecar writes to tmp so the orchestrator can persist the HITL file.
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    model_calls, model_caller = _blocking_hitl_model_caller()
    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
            "hitl_wait_timeout_seconds": 10,
        }
    )

    assert result.status == "completed", f"expected completed, got {result.status}"
    assert result.reason_code == "complete_run"
    assert len(model_calls) == 2, "expected exactly 2 model turns (before + after HITL)"

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "completed"
    assert done_doc["status"] == "completed"

    # State.json should reflect final completed status.
    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.status == "completed"


def test_async_hitl_does_not_pause_run(tmp_path: Path, monkeypatch) -> None:
    """Async HITL (wait_for_human=False): run keeps going without polling or pausing."""
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths

    run_id = "run-async-hitl"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    poll_calls: list[Any] = []

    def tracking_list_entries(**_kw: Any) -> list:
        poll_calls.append(True)
        return []

    monkeypatch.setattr(fb_mod, "list_entries", tracking_list_entries)
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    model_calls: list[str] = []

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append(prompt)
        if len(model_calls) == 1:
            # Async HITL — wait_for_human=False, run keeps going.
            return json.dumps(
                {
                    "action_type": None,
                    "action_inputs": {},
                    "idempotency_key": "ik-async-1",
                    "skip_execution": True,
                    "wait_for_human": False,
                    "complete_run": False,
                    "rationale": "asking human async",
                    "state_patch": None,
                    "continuity_journal_entry": {"stub": True},
                    "operator_progress_message": None,
                    "hitl_request": {
                        "prompt_id": "async-prompt-1",
                        "message": "FYI question",
                        "choices": ["ok"],
                    },
                }
            )
        return json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-async-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "done",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
            }
        )

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
        }
    )

    assert result.status == "completed"
    assert len(model_calls) == 2
    # Runner-level poll_blocking_answer should never have been called (no pause).
    # The feedback store may be polled by the kernel's hitl_poll_feedback_store at
    # the start of each iteration, but that's in-kernel, not the runner-level wait.
    # We just confirm the run completed without the runner entering its pause loop.
    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "completed"


def test_blocking_hitl_timeout_returns_waiting_human(tmp_path: Path, monkeypatch) -> None:
    """Blocking HITL that never gets an answer: runner returns waiting_human after timeout."""
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths
    import harness.runtime.runner.runner as runner_mod

    run_id = "run-hitl-timeout"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    # Feedback store always returns empty — no answer ever arrives.
    monkeypatch.setattr(fb_mod, "list_entries", lambda **_kw: [])
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    # Stub out time.sleep inside the runner so the test doesn't actually wait.
    monkeypatch.setattr(runner_mod.time, "sleep", lambda _s: None)

    model_calls: list[str] = []

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append(prompt)
        return json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-timeout-1",
                "skip_execution": True,
                "wait_for_human": True,
                "complete_run": False,
                "rationale": "waiting",
                "state_patch": None,
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
                "hitl_request": {
                    "prompt_id": "prompt-never-answered",
                    "message": "Answer me",
                    "choices": ["yes", "no"],
                },
            }
        )

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
            # Very short timeout so the test exits quickly.
            "hitl_wait_timeout_seconds": 1,
        }
    )

    assert result.status == "waiting_human"
    assert result.reason_code == "waiting_human_feedback"
    assert len(model_calls) == 1  # only one kernel slice ran (before pause)

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "waiting_human"
    assert done_doc["status"] == "waiting_human"


@pytest.mark.parametrize(
    ("command", "status", "reason_code"),
    [
        ("pause", "paused", "paused_by_operator"),
        ("stop", "stopped", "stopped_by_operator"),
    ],
)
def test_blocking_hitl_honors_run_control_while_waiting(
    tmp_path: Path,
    monkeypatch,
    command: str,
    status: str,
    reason_code: str,
) -> None:
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths
    import harness.runtime.runner.runner as runner_mod
    from harness.runtime.control import write_run_control_request

    run_id = f"run-hitl-{command}"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    monkeypatch.setattr(fb_mod, "list_entries", lambda **_kw: [])
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    control_path = cli_run_state.run_dir(run_id) / "control.json"
    wrote_control = {"done": False}

    def fake_sleep(_seconds: float) -> None:
        if not wrote_control["done"]:
            write_run_control_request(
                control_path,
                command=command,
                reason="operator interrupt",
            )
            wrote_control["done"] = True

    monkeypatch.setattr(runner_mod.time, "sleep", fake_sleep)

    model_calls, model_caller = _blocking_hitl_model_caller()
    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
            "hitl_wait_timeout_seconds": 10,
        }
    )

    assert result.status == status
    assert result.reason_code == reason_code
    assert len(model_calls) == 1, "runner should stop waiting without launching a resumed kernel slice"

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    for payload in (result_doc, done_doc):
        assert payload["status"] == status
        assert payload["terminal_class"] == status
        assert payload["reason_code"] == reason_code
        assert payload["resumable"] is True
        assert payload["control_request"]["command"] == command
    assert result_doc["runtime_state"]["blocking_prompt_id"] == "prompt-range-conflict"
    terminal_event = next(e for e in result_doc["trace_events"] if e.get("event_kind") == "terminal_outcome")
    assert terminal_event["reason_code"] == reason_code
    assert terminal_event["payload"]["terminal_class"] == status

    audit_dir = cli_run_state.run_dir(run_id) / "audit"
    audit_index = json.loads((audit_dir / "index.json").read_text(encoding="utf-8"))
    assert audit_index["terminal_class"] == status
    assert audit_index["reason_code"] == reason_code
    audit_turn = json.loads((audit_dir / "turn_0001.json").read_text(encoding="utf-8"))
    assert audit_turn["terminal_decision"] == "wait_for_human"
    event_lines = (audit_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    terminal_override = json.loads(event_lines[-1])
    assert terminal_override["kind"] == "run_terminal_override"
    assert terminal_override["payload"]["terminal_class"] == status
    assert terminal_override["payload"]["reason_code"] == reason_code
    assert terminal_override["session_id"] == run_id
    assert terminal_override["request_id"] == run_id
    timeline = (audit_dir / "human" / "timeline.md").read_text(encoding="utf-8")
    assert "Run-Level Terminal Override" in timeline
    assert f"- terminal_class: {status}" in timeline

    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.status == status


def test_blocking_hitl_respects_logical_max_iterations_across_slices(tmp_path: Path, monkeypatch) -> None:
    """max_iterations is a logical-run budget, not a per-slice budget.

    Scenario: max_iterations=5, first kernel slice reports it used 3 iterations
    and paused on blocking HITL; the resumed slice must receive max_iterations=2
    (5 - 3), not a fresh 5.

    Uses a _run_orchestration mock to test the runner's outer lifecycle logic
    in isolation from LLM compaction or real kernel behaviour.
    """
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths
    import harness.runtime.runner.runner as runner_mod

    run_id = "run-budget-across-slices"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)
    monkeypatch.setattr(fb_mod, "list_entries", lambda **_kw: [
        {"prompt_id": "prompt-budget", "choice": "yes", "submitted_at_epoch_seconds": 1}
    ])
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    # Minimal opaque dict the runner stores as kernel_resume_snapshot.
    # The fake _run_orchestration ignores it; we just need it to be truthy.
    _FAKE_SNAP = {"schema_version": "kernel_resume.v1", "next_iteration": 4, "fake": True}

    captured_max_iterations: list[int] = []
    slice_call: list[int] = [0]

    def fake_run_orchestration(self_ref: Any, *, context: Any, composed: Any, upstream_run_lineage: Any = None) -> Any:
        slice_call[0] += 1
        captured_max_iterations.append(runner_mod._select_max_iterations(context))
        if slice_call[0] == 1:
            # First slice: used 3 iterations, paused on blocking HITL.
            return SimpleNamespace(
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=3,
                session_id="sess-budget",
                run_artifact_ref=None,
                runtime_state={"blocking_prompt_id": "prompt-budget"},
                trace_events=[],
                kernel_resume_snapshot=_FAKE_SNAP,
                latest_refs={},
                terminal_summary=None,
            )
        # Resumed slice: completes in 1 more turn (turn 4 globally).
        return SimpleNamespace(
            terminal_class="completed",
            reason_code="complete_run",
            iterations=4,
            session_id="sess-budget",
            run_artifact_ref=None,
            runtime_state={},
            trace_events=[],
            kernel_resume_snapshot=None,
            latest_refs={},
            terminal_summary="done",
        )

    monkeypatch.setattr(RuntimeRunner, "_run_orchestration", fake_run_orchestration)

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=lambda *a, **kw: "", targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
            "hitl_wait_timeout_seconds": 10,
        }
    )

    assert result.status == "completed"
    assert len(captured_max_iterations) == 2
    # First slice received the full logical budget.
    assert captured_max_iterations[0] == 5
    # Resumed slice received the remaining budget (5 − 3 used = 2).
    assert captured_max_iterations[1] == 2, (
        f"resumed slice max_iterations should be 2 (5 - 3 used), got {captured_max_iterations[1]}"
    )


def test_blocking_hitl_does_not_exceed_budget_when_pause_hits_exact_ceiling(
    tmp_path: Path, monkeypatch
) -> None:
    """A blocking pause on the last allowed iteration must not buy one extra turn.

    Scenario: the first slice pauses at iteration 3 with max_iterations=3. After
    the answer arrives, the runner must mark the logical run exhausted rather
    than launching a resumed slice with an extra iteration.
    """
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths

    run_id = "run-budget-exact-ceiling"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)
    monkeypatch.setattr(
        fb_mod,
        "list_entries",
        lambda **_kw: [{"prompt_id": "prompt-ceiling", "choice": "yes", "submitted_at_epoch_seconds": 1}],
    )
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    fake_snap = {"schema_version": "kernel_resume.v1", "next_iteration": 4, "fake": True}
    slice_call = [0]

    def fake_run_orchestration(self_ref: Any, *, context: Any, composed: Any, upstream_run_lineage: Any = None) -> Any:
        slice_call[0] += 1
        return SimpleNamespace(
            terminal_class="waiting_human",
            reason_code="waiting_human_feedback",
            iterations=3,
            session_id="sess-ceiling",
            run_artifact_ref=None,
            runtime_state={"blocking_prompt_id": "prompt-ceiling"},
            trace_events=[],
            kernel_resume_snapshot=fake_snap,
            latest_refs={},
            terminal_summary=None,
        )

    monkeypatch.setattr(RuntimeRunner, "_run_orchestration", fake_run_orchestration)

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=lambda *a, **kw: "", targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 3,
            "loop_kind": "harness_cli",
            "hitl_wait_timeout_seconds": 10,
        }
    )

    assert result.status == "exhausted"
    assert result.reason_code == "max_iterations_reached"
    assert slice_call[0] == 1, "runner must not launch an extra resumed slice beyond the logical budget"

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["status"] == "exhausted"
    assert result_doc["terminal_class"] == "exhausted"
    assert done_doc["status"] == "exhausted"


def test_blocking_hitl_auto_resumes_when_run_id_not_in_launch_context(tmp_path: Path, monkeypatch) -> None:
    """When launch context omits run_id, runner generates a canonical one and
    uses it consistently for HITL polling — auto-resume must not silently fail.

    Uses a _run_orchestration mock so the test doesn't depend on the real LLM
    infrastructure to exercise the outer lifecycle identity logic.
    """
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths

    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    # Track which run_ids the runner-level poll uses.
    polled_run_ids: list[str] = []

    def tracking_list_entries(*, loop_kind: str, run_id: str) -> list:
        polled_run_ids.append(run_id)
        if run_id:
            return [{"prompt_id": "prompt-no-runid", "choice": "ok", "submitted_at_epoch_seconds": 1}]
        return []

    monkeypatch.setattr(fb_mod, "list_entries", tracking_list_entries)

    _FAKE_SNAP = {"schema_version": "kernel_resume.v1", "next_iteration": 2, "fake": True}
    slice_call: list[int] = [0]

    def fake_run_orchestration(self_ref: Any, *, context: Any, composed: Any, upstream_run_lineage: Any = None) -> Any:
        slice_call[0] += 1
        if slice_call[0] == 1:
            return SimpleNamespace(
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=1,
                session_id="sess-nrid",
                run_artifact_ref=None,
                runtime_state={"blocking_prompt_id": "prompt-no-runid"},
                trace_events=[],
                kernel_resume_snapshot=_FAKE_SNAP,
                latest_refs={},
                terminal_summary=None,
            )
        return SimpleNamespace(
            terminal_class="completed",
            reason_code="complete_run",
            iterations=2,
            session_id="sess-nrid",
            run_artifact_ref=None,
            runtime_state={},
            trace_events=[],
            kernel_resume_snapshot=None,
            latest_refs={},
            terminal_summary="done",
        )

    monkeypatch.setattr(RuntimeRunner, "_run_orchestration", fake_run_orchestration)

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=lambda *a, **kw: "", targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            # Deliberately omit run_id — runner must generate one.
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
            "hitl_wait_timeout_seconds": 10,
        }
    )

    assert result.status == "completed", f"expected completed, got {result.status}"
    assert slice_call[0] == 2  # pause + resume
    # The runner-level poll must have been called with a non-empty run_id.
    assert polled_run_ids, "runner must have polled feedback store during pause"
    assert all(rid for rid in polled_run_ids), "runner must not poll with empty run_id"


def test_hitl_routing_uses_canonical_run_id(tmp_path: Path, monkeypatch) -> None:
    """HITL feedback lookup uses canonical run_id, not request_id_prefix.

    When run_id and request_id_prefix differ, the feedback store must be
    consulted with run_id so that CLI `answer --run-id` matches.
    """
    import services.agent_viewer.feedback_store as fb_mod
    import config.paths as config_paths

    canonical_run_id = "canonical-run-42"
    stale_prefix = "old-prefix-99"  # different from run_id

    _seed_cli_run_state(tmp_path, monkeypatch, canonical_run_id)

    lookup_run_ids: list[str] = []

    def tracking_list_entries(*, loop_kind: str, run_id: str) -> list:
        lookup_run_ids.append(run_id)
        # Return an answer only when queried with the canonical run_id.
        if run_id == canonical_run_id:
            return [{"prompt_id": "prompt-canon", "choice": "yes", "submitted_at_epoch_seconds": 1}]
        return []

    monkeypatch.setattr(fb_mod, "list_entries", tracking_list_entries)
    monkeypatch.setattr(config_paths, "dossiers_artifacts_root", lambda: tmp_path / "artifacts")

    model_calls: list[str] = []

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append(prompt)
        if len(model_calls) == 1:
            return json.dumps(
                {
                    "action_type": None,
                    "action_inputs": {},
                    "idempotency_key": "ik-canon-1",
                    "skip_execution": True,
                    "wait_for_human": True,
                    "complete_run": False,
                    "rationale": "need human",
                    "state_patch": None,
                    "continuity_journal_entry": {"stub": True},
                    "operator_progress_message": None,
                    "hitl_request": {
                        "prompt_id": "prompt-canon",
                        "message": "confirm?",
                        "choices": ["yes", "no"],
                    },
                }
            )
        return json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "ik-canon-2",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "done",
                "state_patch": {"mission": {"work_universe_posture": "audited"}},
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
            }
        )

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))

    result = runner.run(
        launch_context={
            "run_id": canonical_run_id,
            "request_id_prefix": stale_prefix,  # explicitly different
            "model": "gpt-5.4-mini",
            "max_iterations": 5,
            "loop_kind": "harness_cli",
            "hitl_wait_timeout_seconds": 10,
        }
    )

    assert result.status == "completed", f"expected completed, got {result.status}"
    # The runner's poll_blocking_answer must have been called with the canonical run_id.
    runner_level_lookups = [rid for rid in lookup_run_ids if rid == canonical_run_id]
    assert runner_level_lookups, "runner must query feedback store with canonical run_id"
    # Crucially, the stale prefix must NOT have been used for the runner-level lookup.
    assert stale_prefix not in lookup_run_ids or canonical_run_id in lookup_run_ids


# ---------------------------------------------------------------------------
# Workstream 4 / MAPDEP-BR-014 / MODEL-BR-001: default model is Muse Spark 1.3
# ---------------------------------------------------------------------------


def test_runner_default_model_is_muse_spark_1_3_contributor(monkeypatch) -> None:
    """Omitting model in launch context should resolve to Muse Spark 1.3 Contributor."""
    monkeypatch.delenv("HARNESS_CLI_MODEL", raising=False)
    assert runner_module.DEFAULT_HARNESS_MODEL == "muse-spark-1.3-contributor"
    assert runner_module._select_model_name({}) == "muse-spark-1.3-contributor"
    assert runner_module._select_model_name({"model": None}) == "muse-spark-1.3-contributor"
    assert runner_module._select_model_name({"model": ""}) == "muse-spark-1.3-contributor"
    assert runner_module._select_model_name({"model": "   "}) == "muse-spark-1.3-contributor"


def test_runner_explicit_model_override_is_preserved() -> None:
    """Explicit model override should be respected and not replaced with default."""
    assert runner_module._select_model_name({"model": "gpt-5.4-mini"}) == "gpt-5.4-mini"
    assert runner_module._select_model_name({"model": "gpt-5.4"}) == "gpt-5.4"
    assert runner_module._select_model_name({"model": "gpt-5.6-terra"}) == "gpt-5.6-terra"
    assert runner_module._select_model_name({"model": "gpt-5.6-luna"}) == "gpt-5.6-luna"
    assert (
        runner_module._select_model_name({"model": "muse-spark-1.2-contributor"})
        == "muse-spark-1.2-contributor"
    )
    assert (
        runner_module._select_model_name({"model": "muse-spark-1.3-contributor"})
        == "muse-spark-1.3-contributor"
    )
    assert runner_module._select_model_name({"model": "gpt-5"}) == "gpt-5"


# ---------------------------------------------------------------------------
# Upstream run lineage
# ---------------------------------------------------------------------------


def _upstream_lineage() -> dict:
    return {
        "schema_version": "upstream_run_lineage.v1",
        "upstream_runs": [
            {
                "run_id": "practice-row-live-20260619-76",
                "domain_id": "transcript_edit",
                "relation": "input_handoff",
                "handoff_refs": [
                    "transcript_edit:output",
                    "transcript_edit:resolution_state:practice-row-live-20260619-76",
                ],
            }
        ],
    }


def test_runner_strips_upstream_lineage_from_adapter_context_and_prompt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    model_calls: list[str] = []
    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    run_id = "downstream-lineage-run"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append(prompt)
        return json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "plan-complete",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "done",
                "state_patch": None,
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
            }
        )

    runner = RuntimeRunner(adapter=adapter, model_caller=model_caller, targets=_targets(tmp_path))
    runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 2,
            "upstream_run_lineage": _upstream_lineage(),
        }
    )

    assert adapter.calls
    assert "upstream_run_lineage" not in adapter.calls[0]
    assert "practice-row-live-20260619-76" not in model_calls[0]


def test_runner_persists_upstream_lineage_in_state_result_done_and_audit_index(
    tmp_path: Path,
    monkeypatch,
) -> None:
    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    run_id = "downstream-lineage-persist"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    runner = RuntimeRunner(
        adapter=adapter,
        model_caller=lambda *_a, **_k: json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "plan-complete",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "done",
                "state_patch": None,
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
            }
        ),
        targets=_targets(tmp_path),
    )
    result = runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 2,
            "upstream_run_lineage": _upstream_lineage(),
        }
    )

    state = cli_run_state.read_state(run_id)
    assert state is not None
    assert state.extra["upstream_run_lineage"] == _upstream_lineage()

    result_doc = json.loads((tmp_path / "result.json").read_text(encoding="utf-8"))
    done_doc = json.loads((tmp_path / "done.json").read_text(encoding="utf-8"))
    assert result_doc["upstream_run_lineage"] == _upstream_lineage()
    assert done_doc["upstream_run_lineage"] == _upstream_lineage()

    audit_index = json.loads((cli_run_state.run_dir(run_id) / "audit" / "index.json").read_text(encoding="utf-8"))
    assert audit_index["upstream_run_lineage"] == _upstream_lineage()
    assert "transcript_edit:output" not in audit_index["latest_refs"]
    assert result.result_payload["latest_refs"] == audit_index["latest_refs"]

    stale = cli_run_state.read_state(run_id)
    assert stale is not None
    stale.extra = {"model": "gpt-5.4-mini"}
    cli_run_state.write_state(stale)

    runner._write_artifacts(
        targets=_targets(tmp_path),
        result=result,
    )
    restored = cli_run_state.read_state(run_id)
    assert restored is not None
    assert restored.extra["upstream_run_lineage"] == _upstream_lineage()


def test_runner_resume_spawn_argv_preserves_upstream_lineage_without_adapter_exposure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import harness.cli.run_layout as layout_mod

    monkeypatch.setattr(layout_mod, "cli_runs_root", lambda: tmp_path / "cli_runs")
    lineage = _upstream_lineage()
    launch = {
        "run_id": "downstream-resume",
        "upstream_run_lineage": lineage,
        "model": "gpt-5.4-mini",
    }
    spawn_argv = [
        "python",
        "-m",
        "harness.runtime.runner.entrypoint",
        "--launch-context-json",
        json.dumps(launch, separators=(",", ":")),
    ]
    state = cli_run_state.new_run_state(
        run_id="downstream-resume",
        pid=1,
        loop_kind="deed_to_ir",
        mode="live",
        spawn_argv=spawn_argv,
        status="started",
        extra={"upstream_run_lineage": lineage},
    )
    cli_run_state.write_state(state)

    loaded = cli_run_state.read_state("downstream-resume")
    assert loaded is not None
    assert loaded.extra["upstream_run_lineage"] == lineage
    assert "upstream_run_lineage" in loaded.spawn_argv[-1]

    _, domain_context = __import__(
        "harness.runtime.upstream_run_lineage",
        fromlist=["partition_launch_context_for_upstream_lineage"],
    ).partition_launch_context_for_upstream_lineage(launch)
    assert "upstream_run_lineage" not in domain_context


def test_runner_timeline_includes_upstream_link_when_local_audit_exists(
    tmp_path: Path,
    monkeypatch,
) -> None:
    upstream_id = "practice-row-live-20260619-76"
    upstream_run_dir = tmp_path / "cli_runs" / upstream_id
    upstream_run_dir.mkdir(parents=True)
    (upstream_run_dir / "state.json").write_text(
        json.dumps({"run_id": upstream_id}),
        encoding="utf-8",
    )
    upstream_timeline = upstream_run_dir / "audit" / "human" / "timeline.md"
    upstream_timeline.parent.mkdir(parents=True)
    upstream_timeline.write_text("# upstream", encoding="utf-8")

    adapter = FakeSurfaceAdapter(calls=[], surface=_surface([]))
    run_id = "downstream-with-link"
    _seed_cli_run_state(tmp_path, monkeypatch, run_id)

    runner = RuntimeRunner(
        adapter=adapter,
        model_caller=lambda *_a, **_k: json.dumps(
            {
                "action_type": None,
                "action_inputs": {},
                "idempotency_key": "plan-complete",
                "skip_execution": True,
                "wait_for_human": False,
                "complete_run": True,
                "rationale": "done",
                "state_patch": None,
                "continuity_journal_entry": {"stub": True},
                "operator_progress_message": None,
            }
        ),
        targets=_targets(tmp_path),
    )
    runner.run(
        launch_context={
            "run_id": run_id,
            "model": "gpt-5.4-mini",
            "max_iterations": 2,
            "upstream_run_lineage": _upstream_lineage(),
        }
    )

    timeline = (cli_run_state.run_dir(run_id) / "audit" / "human" / "timeline.md").read_text(
        encoding="utf-8"
    )
    assert "## Upstream Runs" in timeline
    assert "[open upstream timeline]" in timeline
    assert upstream_timeline.read_text(encoding="utf-8") == "# upstream"
