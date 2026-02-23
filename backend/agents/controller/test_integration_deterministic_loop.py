from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from typing import Any, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import config.paths as legacy_paths
from backend.agent_kernel.actions import ActionExecutor, ActionExecutorDeps, Compiler, Judge
from backend.agent_kernel.models import (
    KernelBudgets,
    KernelGoal,
    KernelSessionStartRequest,
    StopReason,
    TerminalOutcomeKind,
)
from backend.agent_kernel.run_artifact import ArtifactRef, RunArtifact
from backend.agent_kernel.session import KernelSessionManager
from backend.agents.controller.controller import run_controller_loop


class _DeterministicServices(Compiler, Judge):
    def compile(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/compile/compile-001.json")

    def judge(self, inputs: Mapping[str, Any]) -> ArtifactRef:
        del inputs
        return ArtifactRef(artifact_path="artifacts/judge/judge-001.json")


class _InMemorySessionPersistence:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], RunArtifact] = {}

    def save_run_artifact(self, run_artifact: RunArtifact) -> dict[str, object]:
        key = (run_artifact.request_id, run_artifact.run_id)
        self._store[key] = RunArtifact.model_validate(run_artifact.model_dump(mode="json"))
        return {"path": f"in-memory://{run_artifact.request_id}/{run_artifact.run_id}.json"}

    def get_run_artifact(self, request_id: str, run_id: str) -> RunArtifact | None:
        return self._store.get((request_id, run_id))


class _SequenceLLM:
    def __init__(self) -> None:
        self._responses = [
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k-001",
                    "args": {},
                    "why": "attempt done early",
                    "declare_done": {
                        "artifact_refs": {"ir_ref": "ir://placeholder"},
                        "evidence_links": [],
                        "accepted_deviations": [],
                    },
                },
            },
            {
                "structured_data": {
                    "action_type": "compile",
                    "idempotency_key": "k-002",
                    "args": {"ir_artifact_ref": "ir://placeholder"},
                    "why": "compile now",
                }
            },
            {
                "structured_data": {
                    "action_type": "judge",
                    "idempotency_key": "k-003",
                    "args": {"ir_artifact_ref": "ir://placeholder"},
                    "why": "judge now",
                }
            },
            {
                "structured_data": {
                    "action_type": "declare_done",
                    "idempotency_key": "k-004",
                    "args": {},
                    "why": "declare done after gates",
                    "declare_done": {
                        "artifact_refs": {
                            "ir_ref": "ir://placeholder",
                            "compile_ref": "artifacts/compile/compile-001.json",
                            "judge_ref": "artifacts/judge/judge-001.json",
                        },
                        "evidence_links": [],
                        "accepted_deviations": [],
                    },
                },
            },
        ]
        self._i = 0

    def propose_next_step(
        self,
        *,
        model: str,
        tools: list[object],
        tool_choice_name: str,
        developer_message: str,
        user_message: str,
    ) -> dict[str, object]:
        del model, tools, tool_choice_name, developer_message, user_message
        idx = min(self._i, len(self._responses) - 1)
        self._i += 1
        return self._responses[idx]


def test_deterministic_controller_loop_reaches_success_with_refusal_then_compile_judge() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        original = legacy_paths.dossiers_root

        def _patched_root() -> Path:
            return root / "dossiers_data"

        legacy_paths.dossiers_root = _patched_root  # type: ignore[assignment]
        try:
            services = _DeterministicServices()
            executor = ActionExecutor(deps=ActionExecutorDeps(compiler=services, judge=services))
            persistence = _InMemorySessionPersistence()
            manager = KernelSessionManager(action_executor=executor, persistence_service=persistence)
            llm = _SequenceLLM()
            start_request = KernelSessionStartRequest(
                request_id="det-run-001",
                goal=KernelGoal(requires_global_placement=False, objective="deterministic integration test"),
                budgets=KernelBudgets(
                    max_steps=10,
                    max_wall_time_seconds=120,
                    max_retrieval_calls=5,
                    max_semantic_calls=5,
                    max_patch_calls=5,
                ),
                initial_graph_json={"graph_id": "g1", "nodes": [], "edges": [], "metadata": {}},
            )
            result = run_controller_loop(
                session_manager=manager,
                llm_client=llm,  # type: ignore[arg-type]
                start_request=start_request,
                max_iterations=8,
            )
            assert result.terminal.terminal_outcome == TerminalOutcomeKind.SUCCESS
            assert result.terminal.stop_reason == StopReason.COMPLETED
            assert Path(result.transcript_artifact_ref).exists()
            transcript = json.loads(Path(result.transcript_artifact_ref).read_text(encoding="utf-8"))
            states = [
                event["detail"]
                for event in transcript["events"]
                if event.get("event_type") == "kernel_step_result"
            ]
            assert "refused" in states
            assert "executed" in states
        finally:
            legacy_paths.dossiers_root = original  # type: ignore[assignment]
