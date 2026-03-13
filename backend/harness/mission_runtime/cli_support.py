from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from agent_kernel.session import KernelSessionManager
from agent_kernel.tooling import (
    TranscriptAuditTool,
    TranscriptEditPlanApplyTool,
    TranscriptImageVerificationTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanOpenerTool,
    TranscriptSpanSeedsSaverTool,
)
from agents.controller.bootstrap import (
    hydrate_and_persist_finalized_dossier_text,
    persist_deed_text_artifact,
)
from agents.controller.openai_client import OpenAINextStepClient
from agents.transcript_edit.contracts import TranscriptEditAgentRunRequest
from agents.transcript_edit.controller import run_transcript_edit_controller_loop
from agents.transcript_edit.hitl_feedback import poll_feedback_response, viewer_run_id_from_request_prefix
from agents.transcript_edit.state_projection import derive_waiting_feedback_projection
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService

from .hitl_watch import hitl_pending_path

from .contracts import MissionRuntimeCycleResult, MissionRuntimeRequest, ModePolicy
from .modes import (
    DeedToIRModePolicy,
    TranscriptEditModePolicy,
    build_deed_to_ir_mode_policy_from_controller_inputs,
)
from .runtime import build_mission_observability_payload


@dataclass(frozen=True)
class DeedModeCliInputs:
    dossier_id: str | None
    deed_text: str | None
    initial_ir_ref: str | None
    model: str
    max_iterations: int
    requires_global_placement: bool
    render_required: bool


@dataclass(frozen=True)
class TranscriptModeCliInputs:
    dossier_id: str | None
    source_transcript_ref: str | None
    source_text: str | None
    model: str
    max_iterations: int
    mode: str
    validation_mode: str
    auto_promote: bool


def build_deed_mode_policy_from_cli_inputs(inputs: DeedModeCliInputs) -> DeedToIRModePolicy:
    start_request = build_deed_mode_start_request(inputs=inputs)
    session_manager = KernelSessionManager(persistence_service=RunArtifactPersistenceService())
    llm_client = OpenAINextStepClient()
    return build_deed_to_ir_mode_policy_from_controller_inputs(
        session_manager=session_manager,
        llm_client=llm_client,
        start_request=start_request,
        model=inputs.model,
        max_iterations=max(1, int(inputs.max_iterations)),
    )


def build_deed_mode_start_request(*, inputs: DeedModeCliInputs) -> KernelSessionStartRequest:
    request_id = f"mission-runtime-cli-{uuid4().hex[:8]}"
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


def build_transcript_mode_policy_from_cli_inputs(
    *,
    inputs: TranscriptModeCliInputs,
    mission_request: MissionRuntimeRequest,
) -> TranscriptEditModePolicy:
    session_manager = KernelSessionManager(
        action_executor=ActionExecutor(
            deps=ActionExecutorDeps(
                transcript_auditor=TranscriptAuditTool(),
                transcript_span_opener=TranscriptSpanOpenerTool(),
                transcript_image_verifier=TranscriptImageVerificationTool(),
                transcript_plan_applier=TranscriptEditPlanApplyTool(),
                transcript_span_seeds_saver=TranscriptSpanSeedsSaverTool(),
                transcript_promoter=TranscriptMappingPromoterTool(),
            )
        ),
        persistence_service=RunArtifactPersistenceService(),
    )
    request_prefix = f"mission-{mission_request.mission_id}-tx"

    # Write HITL events to a well-known file so hitl_watch can detect them for agent-mode testing.
    _hitl_file = hitl_pending_path(request_prefix)

    def _progress_cb(event: dict[str, Any]) -> None:
        if not (isinstance(event, dict) and event.get("event_type") == "human_feedback_needed"):
            return
        try:
            import json as _json
            _hitl_file.parent.mkdir(parents=True, exist_ok=True)
            _hitl_file.write_text(_json.dumps(dict(event), ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    def _runner(request: MissionRuntimeRequest, ledger: Any) -> Any:
        import time

        resolved_source_ref = inputs.source_transcript_ref or infer_transcript_ref_from_ledger(ledger)
        run_request = TranscriptEditAgentRunRequest(
            dossier_id=inputs.dossier_id,
            source_transcript_ref=resolved_source_ref,
            source_text=inputs.source_text,
            model=inputs.model,
            max_iterations=inputs.max_iterations,
            mode=inputs.mode,
            validation_mode=inputs.validation_mode,
            auto_promote=inputs.auto_promote,
            trigger=f"mission_runtime_cli:{request.initial_mode}",
        )
        if not run_request.source_transcript_ref and not run_request.source_text:
            raise ValueError(
                "transcript_edit_mode_requires_source_transcript_ref_or_source_text "
                "(provide --tx-source-transcript-ref/--tx-text or ensure transition handoff refs include a transcript ref)"
            )

        viewer_run_id = viewer_run_id_from_request_prefix(request_prefix)
        _MAX_HITL_RESUME_ROUNDS = 10
        _FEEDBACK_POLL_INTERVAL = 2.0
        _FEEDBACK_POLL_TIMEOUT = 600

        for _round in range(_MAX_HITL_RESUME_ROUNDS):
            result = run_transcript_edit_controller_loop(
                session_manager=session_manager,
                request=run_request,
                request_id_prefix=request_prefix,
                progress_cb=_progress_cb,
                startup_countdown_seconds=0,
            )

            # If not waiting for feedback, we're done.
            hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
            blocker_registry = hitl_state.get("blocker_registry") if isinstance(hitl_state.get("blocker_registry"), dict) else {}
            waiting_projection = derive_waiting_feedback_projection(
                blocker_registry=blocker_registry,
                fallback_prompt_id=str(hitl_state.get("pending_feedback_prompt_id") or "").strip() or None,
                fallback_decision_key=str(hitl_state.get("pending_feedback_decision_key") or "").strip().lower() or None,
            )
            if not waiting_projection.get("waiting_feedback"):
                return result

            prompt_id = str(waiting_projection.get("pending_feedback_prompt_id") or "").strip() or None
            if not prompt_id:
                return result  # Cannot resume without a prompt_id.

            # Block-poll the feedback store until the tester injects a response.
            # hitl_watch will have already surfaced the HITL event; we just wait here.
            deadline = time.time() + _FEEDBACK_POLL_TIMEOUT
            feedback_entry: dict[str, Any] | None = None
            while time.time() < deadline:
                feedback_entry = poll_feedback_response(run_id=viewer_run_id, prompt_id=prompt_id)
                if feedback_entry is not None:
                    break
                time.sleep(_FEEDBACK_POLL_INTERVAL)

            if feedback_entry is None:
                return result  # Timed out waiting for feedback.

            # Resume the controller with the injected feedback as the authority.
            resume_decision_key = (
                str(waiting_projection.get("pending_feedback_decision_key") or "").strip().lower() or None
            )
            run_request = run_request.model_copy(update={
                "resume_pending_feedback_prompt_id": prompt_id,
                "resume_pending_feedback_decision_key": resume_decision_key,
                "resume_blocker_registry": blocker_registry if blocker_registry else None,
            })

        return result  # Max HITL resume rounds reached.

    return TranscriptEditModePolicy(runner=_runner)


def infer_transcript_ref_from_ledger(ledger: Any) -> str | None:
    refs = getattr(ledger, "high_signal_artifact_refs", ())
    if not isinstance(refs, tuple):
        return None
    for candidate in reversed(refs):
        if not isinstance(candidate, str):
            continue
        text = candidate.strip()
        if not text:
            continue
        if "transcript" in text.lower():
            return text
    return None


def build_mission_cli_payload(
    *,
    mission_request: MissionRuntimeRequest,
    ledger: Any,
    cycle_results: list[MissionRuntimeCycleResult],
) -> dict[str, Any]:
    observability_payload = build_mission_observability_payload(
        request=mission_request,
        ledger=ledger,
        cycle_results=cycle_results,
    )
    return {
        "cli_surface": "mission_runtime_cli",
        "canonical_surface": True,
        "mission_runtime": observability_payload.get("mission_runtime"),
    }


def build_policy_list_for_cli(
    *,
    mission_request: MissionRuntimeRequest,
    deed_inputs: DeedModeCliInputs | None,
    transcript_inputs: TranscriptModeCliInputs | None,
) -> list[ModePolicy]:
    policies: list[ModePolicy] = []
    needs_deed = (
        mission_request.initial_mode == "deed_to_ir"
        or bool(mission_request.metadata.get("transcript_edit_transition_to_deed_to_ir"))
    )
    needs_tx = (
        mission_request.initial_mode == "transcript_edit"
        or bool(mission_request.metadata.get("deed_to_ir_transition_to_transcript_edit"))
    )
    if needs_deed:
        if deed_inputs is None:
            raise ValueError("deed_mode_inputs_required")
        policies.append(build_deed_mode_policy_from_cli_inputs(deed_inputs))
    if needs_tx:
        if transcript_inputs is None:
            raise ValueError("transcript_mode_inputs_required")
        policies.append(
            build_transcript_mode_policy_from_cli_inputs(
                inputs=transcript_inputs,
                mission_request=mission_request,
            )
        )
    return policies
