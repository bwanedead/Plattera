"""Retired compatibility shell for the old Agent Kernel v0 JSON loop.

Canonical shared integration is now harness-native step execution plus harness runtime.
This module is intentionally severed from feature-graph compatibility code so dormant
product residue cannot keep an implicit bridge into the active harness path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .actions import ActionExecutor
from .models import KernelRequest, KernelResult, StopReason, TerminalOutcomeKind
from .policies import KernelPolicy
from .run_artifact import ArtifactRef, RunArtifact


class RunArtifactPersistence(Protocol):
    """Minimal persistence protocol used by compatibility callers."""

    def save_run_artifact(self, run_artifact: RunArtifact) -> dict[str, object]: ...


class IRGraphLoader(Protocol):
    """Dependency boundary for reading graph JSON from an IR artifact reference."""

    def load_graph(self, ir_artifact_ref: ArtifactRef) -> dict[str, object]: ...


class FileSystemIRGraphLoader:
    """Default filesystem-based loader for IR/graph JSON artifacts."""

    def load_graph(self, ir_artifact_ref: ArtifactRef) -> dict[str, object]:
        import json

        payload = json.loads(Path(ir_artifact_ref.artifact_path).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            graph_payload = payload.get("graph")
            if isinstance(graph_payload, dict):
                return graph_payload
            return payload
        raise ValueError("ir_artifact_payload_not_object")


@dataclass(frozen=True)
class KernelLoopOutput:
    """Output tuple for library callers: result envelope plus durable run artifact."""

    kernel_result: KernelResult
    run_artifact: RunArtifact


class KernelLoop:
    """Retired compatibility wrapper kept only for explicit failure surfaces."""

    def __init__(
        self,
        *,
        policy: KernelPolicy | None = None,
        action_executor: ActionExecutor | None = None,
        persistence_service: RunArtifactPersistence | None = None,
        ir_graph_loader: IRGraphLoader | None = None,
        no_progress_max_stagnant_repair_cycles: int = 2,
        run_id_factory: Callable[[KernelRequest], str] | None = None,
    ) -> None:
        self._policy = policy
        self._action_executor = action_executor or ActionExecutor()
        self._persistence_service = persistence_service
        self._ir_graph_loader = ir_graph_loader or FileSystemIRGraphLoader()
        self._no_progress_max_stagnant_repair_cycles = no_progress_max_stagnant_repair_cycles
        self._run_id_factory = run_id_factory or (lambda request: f"{request.request_id}-run-001")

    def run(self, request: KernelRequest) -> KernelLoopOutput:
        del request
        raise RuntimeError(
            "agent_kernel_compatibility_loop_retired:"
            "feature_graph_bridge_severed:"
            "use_harness_native_execution_and_runtime"
        )


def run_kernel(
    request: KernelRequest,
    *,
    policy: KernelPolicy | None = None,
    action_executor: ActionExecutor | None = None,
    persistence_service: RunArtifactPersistence | None = None,
    ir_graph_loader: IRGraphLoader | None = None,
    no_progress_max_stagnant_repair_cycles: int = 2,
    run_id_factory: Callable[[KernelRequest], str] | None = None,
) -> KernelLoopOutput:
    """Retired one-shot compatibility entrypoint."""
    loop = KernelLoop(
        policy=policy,
        action_executor=action_executor,
        persistence_service=persistence_service,
        ir_graph_loader=ir_graph_loader,
        no_progress_max_stagnant_repair_cycles=no_progress_max_stagnant_repair_cycles,
        run_id_factory=run_id_factory,
    )
    return loop.run(request)


def _extract_artifact_ref(outputs: dict[str, object], key: str) -> ArtifactRef | None:
    raw = outputs.get(key)
    if isinstance(raw, ArtifactRef):
        return raw
    if isinstance(raw, dict):
        return ArtifactRef.model_validate(raw)
    if isinstance(raw, str) and raw:
        return ArtifactRef(artifact_path=raw)
    return None


def _find_missing_capability_reason(reason_codes: list[str]) -> str | None:
    for code in reason_codes:
        if code.startswith("missing_"):
            return code
    return None


def _find_worker_unavailable_reason(reason_codes: list[str]) -> str | None:
    for code in reason_codes:
        if code in {
            "semantic_worker_unavailable",
            "semantic_worker_backoff",
            "semantic_worker_in_backoff",
            "semantic_worker_port_in_use",
            "semantic_worker_timeout",
        }:
            return code
    return None


def _coerce_graph_payload(raw_graph: dict[str, object] | None) -> dict[str, object] | None:
    if not isinstance(raw_graph, dict):
        return None
    return dict(raw_graph)


def _classify_terminal_outcome(stop_reason: StopReason) -> TerminalOutcomeKind:
    if stop_reason == StopReason.COMPLETED:
        return TerminalOutcomeKind.SUCCESS
    if stop_reason == StopReason.VALIDATION_FAILED:
        return TerminalOutcomeKind.PARTIAL
    if stop_reason == StopReason.NEEDS_USER_CHOICE:
        return TerminalOutcomeKind.NEEDS_USER_CHOICE
    if stop_reason == StopReason.NEEDS_UPLOAD:
        return TerminalOutcomeKind.NEEDS_UPLOAD
    return TerminalOutcomeKind.FAILED
