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
                    "state_patch": {
                        "resolution": {
                            "items": [
                                {
                                    "item_id": "peer_alpha_review",
                                    "title": "Peer alpha review",
                                    "kind": "work_unit",
                                    "status": "closed",
                                }
                            ]
                        },
                        "mission": {
                            "work_universe_posture": "audited",
                            "closure_state": {
                                "overall_status": "complete_ready",
                                "ready_to_close": True,
                                "dimensions": [
                                {
                                    "dimension_id": "layer_1_delta_convergence",
                                    "title": "Layer 1",
                                    "status": "closed",
                                },
                                {
                                    "dimension_id": "layer_2_intrinsic_source_integrity",
                                    "title": "Layer 2",
                                    "status": "open",
                                },
                                {
                                    "dimension_id": "layer_3_external_dependency_completeness",
                                    "title": "Layer 3",
                                    "status": "no_further_progress",
                                },
                                {
                                    "dimension_id": "layer_4_mapping_blocking_relevance",
                                    "title": "Layer 4",
                                    "status": "non_blocking",
                                    "blocking": False,
                                },
                            ],
                        }
                    }
                },
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


def test_runner_injects_domain_closure_policy_into_orchestration_context(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, Any] = {}
    policy = DomainClosurePolicy(
        hard_enforced=True,
        enforce_on_complete=True,
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
    assert captured["domain_closure_policy"]["required_dimension_ids"] == ["layer_a"]


# ── HITL lifecycle tests ───────────────────────────────────────────────────────


def _blocking_hitl_model_caller() -> tuple[list[str], Any]:
    """Return (model_calls list, model_caller) where turn 1 emits blocking HITL, turn 2 completes."""
    model_calls: list[str] = []

    def model_caller(prompt: str, model: str, **_kwargs: Any) -> str:
        model_calls.append(prompt)
        if len(model_calls) == 1:
            return json.dumps(
                {
                    "action_type": "noop",
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
                "action_type": "noop",
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
                    "action_type": "noop",
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
                "action_type": "noop",
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
                "action_type": "noop",
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

    def fake_run_orchestration(self_ref: Any, *, context: Any, composed: Any) -> Any:
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

    def fake_run_orchestration(self_ref: Any, *, context: Any, composed: Any) -> Any:
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

    def fake_run_orchestration(self_ref: Any, *, context: Any, composed: Any) -> Any:
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
                    "action_type": "noop",
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
                "action_type": "noop",
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
# Workstream 4: default model is gpt-5.4
# ---------------------------------------------------------------------------


def test_runner_default_model_is_gpt54() -> None:
    """Omitting model in launch context should resolve to gpt-5.4, not gpt-5.4-mini."""
    assert runner_module._select_model_name({}) == "gpt-5.4"
    assert runner_module._select_model_name({"model": None}) == "gpt-5.4"
    assert runner_module._select_model_name({"model": ""}) == "gpt-5.4"


def test_runner_explicit_model_override_is_preserved() -> None:
    """Explicit model override should be respected and not replaced with default."""
    assert runner_module._select_model_name({"model": "gpt-5.4-mini"}) == "gpt-5.4-mini"
    assert runner_module._select_model_name({"model": "gpt-5"}) == "gpt-5"
