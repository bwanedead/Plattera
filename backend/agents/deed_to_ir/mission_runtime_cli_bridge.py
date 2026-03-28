from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from feature_graph.kernel_executor_composition import build_plattera_default_kernel_session_manager
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService

from agents.controller.bootstrap import hydrate_and_persist_finalized_dossier_text, persist_deed_text_artifact
from agents.controller.openai_client import OpenAINextStepClient
from harness.mission_runtime.contracts import MissionRuntimeRequest

from .mission_runtime_bridge import build_deed_to_ir_mode_adapter_from_controller_inputs


@dataclass(frozen=True)
class DeedModeCliInputs:
    dossier_id: str | None
    deed_text: str | None
    initial_ir_ref: str | None
    model: str
    max_iterations: int
    requires_global_placement: bool
    render_required: bool


def build_deed_mode_adapter_from_cli_inputs(
    inputs: DeedModeCliInputs,
    *,
    mission_request: MissionRuntimeRequest | None = None,
):
    session_manager = build_plattera_default_kernel_session_manager(
        persistence_service=RunArtifactPersistenceService()
    )
    llm_client = OpenAINextStepClient()
    mission_id = str(getattr(mission_request, "mission_id", None) or "").strip() or None

    def _build_start_request(request: MissionRuntimeRequest, ledger: Any) -> KernelSessionStartRequest:
        resolved_mission_id = mission_id or str(getattr(request, "mission_id", None) or "").strip() or None
        inferred_ir_ref = inputs.initial_ir_ref or infer_deed_ir_ref_from_ledger(ledger)
        return build_deed_mode_start_request(
            inputs=dataclasses.replace(inputs, initial_ir_ref=inferred_ir_ref),
            mission_id=resolved_mission_id,
        )

    return build_deed_to_ir_mode_adapter_from_controller_inputs(
        session_manager=session_manager,
        llm_client=llm_client,
        start_request_factory=_build_start_request,
        model=inputs.model,
        max_iterations=max(1, int(inputs.max_iterations)),
    )


def build_deed_mode_start_request(*, inputs: DeedModeCliInputs, mission_id: str | None = None) -> KernelSessionStartRequest:
    prefix = f"mission-{mission_id}-deed" if mission_id else "mission-deed"
    request_id = f"{prefix}-{uuid4().hex[:6]}"
    initial_graph_json: dict[str, Any] | None = None
    bootstrap_metadata: dict[str, Any] = {"source": "mission_runtime_cli_bootstrap", "dossier_id": inputs.dossier_id}
    deed_text = str(inputs.deed_text or "").strip()
    if deed_text:
        deed_artifact = persist_deed_text_artifact(
            request_id=request_id,
            deed_text=deed_text,
            dossier_id=inputs.dossier_id,
        )
        bootstrap_metadata["source"] = "mission_runtime_cli_text_bootstrap"
        bootstrap_metadata["deed_text_excerpt"] = deed_artifact.excerpt
        bootstrap_metadata["deed_text_artifact_ref"] = deed_artifact.artifact_path
    elif inputs.dossier_id:
        deed_artifact = hydrate_and_persist_finalized_dossier_text(
            request_id=request_id,
            dossier_id=inputs.dossier_id,
        )
        if deed_artifact is not None:
            bootstrap_metadata["source"] = "mission_runtime_cli_dossier_bootstrap"
            bootstrap_metadata["deed_text_excerpt"] = deed_artifact.excerpt
            bootstrap_metadata["deed_text_artifact_ref"] = deed_artifact.artifact_path

    if bootstrap_metadata:
        initial_graph_json = {
            "graph_id": f"graph_{request_id}",
            "nodes": [],
            "edges": [],
            "metadata": bootstrap_metadata,
        }
    return KernelSessionStartRequest(
        request_id=request_id,
        goal=KernelGoal(
            requires_global_placement=bool(inputs.requires_global_placement),
            render_required=bool(inputs.render_required),
            objective="mission_runtime_cli_run",
        ),
        budgets=KernelBudgets(
            max_steps=30,
            max_wall_time_seconds=600,
            max_retrieval_calls=12,
            max_semantic_calls=8,
            max_patch_calls=8,
        ),
        dossier_id=inputs.dossier_id,
        source_entry_ref=(f"final:{inputs.dossier_id}" if inputs.dossier_id else None),
        initial_ir_ref=inputs.initial_ir_ref,
        initial_graph_json=initial_graph_json,
    )


def infer_deed_ir_ref_from_ledger(ledger: Any) -> str | None:
    refs = getattr(ledger, "high_signal_artifact_refs", ())
    if not isinstance(refs, tuple):
        return None
    for candidate in reversed(refs):
        if not isinstance(candidate, str):
            continue
        text = candidate.strip()
        lower = text.lower()
        if text and ("ir" in lower or "graph" in lower) and "transcript" not in lower:
            return text
    return None
