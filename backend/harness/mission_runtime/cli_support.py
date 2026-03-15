from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path
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
    TranscriptOrientBaselineTool,
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
from .modes.transcript_edit import run_orchestration_kernel_transcript_loop
from .runtime import build_mission_observability_payload

# ---------------------------------------------------------------------------
# Named scenario registry (D3 — practice deed scenarios)
# ---------------------------------------------------------------------------

# Canonical dossier id for the legal-text image practice scenario.
_PRACTICE_LEGALTEXT_DOSSIER_ID = "live-validation-practice-legaltext"
# Seed filename to search for inside the dossier's transcript sub-tree.
_PRACTICE_LEGALTEXT_SEED_FILENAME = "draft_legal_text_image_v2.json"

_TX_KNOWN_SCENARIOS: frozenset[str] = frozenset({"practice_legaltext"})


def resolve_tx_scenario(scenario_name: str) -> tuple[str | None, str | None]:
    """Return ``(dossier_id, transcript_ref)`` for a named CLI test scenario.

    ``transcript_ref`` is an absolute path resolved by searching the local
    dossiers store.  Returns ``(None, None)`` for unknown scenario names.
    The caller is responsible for providing a fallback when ``transcript_ref``
    is ``None`` (e.g. require ``--tx-source-transcript-ref``).

    Currently supported scenarios:
    - ``practice_legaltext`` — legal-text image with known range 74/75 conflict.
      See docs/transcript-edit-live-validation-path-2026-03-08.md for expected
      lifecycle.
    """
    if scenario_name not in _TX_KNOWN_SCENARIOS:
        return None, None

    if scenario_name == "practice_legaltext":
        dossier_id = _PRACTICE_LEGALTEXT_DOSSIER_ID
        transcript_ref = _find_practice_legaltext_transcript()
        return dossier_id, transcript_ref

    return None, None


def _find_practice_legaltext_transcript() -> str | None:
    """Search dossiers_views_root for the practice legaltext transcript seed.

    Tries the known seed filename first, then falls back to the most recently
    modified raw transcript in the dossier directory.
    Returns an absolute path string, or None if nothing found.
    """
    try:
        from config.paths import dossiers_views_root
    except ModuleNotFoundError:
        from backend.config.paths import dossiers_views_root  # type: ignore[no-redef]
    try:
        dossier_dir = dossiers_views_root() / _PRACTICE_LEGALTEXT_DOSSIER_ID
        if not dossier_dir.exists():
            return None
        # Preferred: locate the known seed filename anywhere under the dossier tree.
        matches = sorted(dossier_dir.rglob(_PRACTICE_LEGALTEXT_SEED_FILENAME))
        if matches:
            return str(matches[-1])
        # Fallback: most recently modified raw transcript file.
        raw_files = sorted(dossier_dir.rglob("raw/*.json"), key=lambda p: p.stat().st_mtime)
        if raw_files:
            return str(raw_files[-1])
    except Exception:
        pass
    return None


@dataclass(frozen=True)
class DeedModeCliInputs:
    dossier_id: str | None
    deed_text: str | None
    initial_ir_ref: str | None
    model: str
    max_iterations: int
    requires_global_placement: bool
    render_required: bool
    use_orchestration_kernel: bool = False


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
    use_orchestration_kernel: bool = False


def build_deed_mode_policy_from_cli_inputs(
    inputs: DeedModeCliInputs,
    *,
    mission_request: MissionRuntimeRequest | None = None,
) -> DeedToIRModePolicy:
    session_manager = KernelSessionManager(persistence_service=RunArtifactPersistenceService())
    llm_client = OpenAINextStepClient()
    _mission_id = str(getattr(mission_request, "mission_id", None) or "").strip() or None

    def _build_start_request(request: MissionRuntimeRequest, ledger: Any) -> KernelSessionStartRequest:
        mid = _mission_id or str(getattr(request, "mission_id", None) or "").strip() or None
        inferred_ir_ref = inputs.initial_ir_ref or infer_deed_ir_ref_from_ledger(ledger)
        return build_deed_mode_start_request(
            inputs=dataclasses.replace(inputs, initial_ir_ref=inferred_ir_ref),
            mission_id=mid,
        )

    return build_deed_to_ir_mode_policy_from_controller_inputs(
        session_manager=session_manager,
        llm_client=llm_client,
        start_request_factory=_build_start_request,
        model=inputs.model,
        max_iterations=max(1, int(inputs.max_iterations)),
        use_orchestration_kernel=bool(inputs.use_orchestration_kernel),
    )


def build_deed_mode_start_request(*, inputs: DeedModeCliInputs, mission_id: str | None = None) -> KernelSessionStartRequest:
    _prefix = f"mission-{mission_id}-deed" if mission_id else "mission-deed"
    request_id = f"{_prefix}-{uuid4().hex[:6]}"
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
                transcript_orient_baseliner=TranscriptOrientBaselineTool(),
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

    def _build_run_request(request: MissionRuntimeRequest, ledger: Any) -> TranscriptEditAgentRunRequest:
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
        return run_request

    if inputs.use_orchestration_kernel:
        def _ok_runner(request: MissionRuntimeRequest, ledger: Any) -> Any:
            import time as _time

            run_request = _build_run_request(request, ledger)
            viewer_run_id = viewer_run_id_from_request_prefix(request_prefix)
            _MAX_HITL_RESUME_ROUNDS = 10
            _FEEDBACK_POLL_INTERVAL = 2.0
            _FEEDBACK_POLL_TIMEOUT = 600

            resume_feedback: dict[str, Any] | None = None
            for _round in range(_MAX_HITL_RESUME_ROUNDS):
                result = run_orchestration_kernel_transcript_loop(
                    session_manager=session_manager,
                    request=run_request,
                    request_id_prefix=request_prefix,
                    planner=None,
                    progress_cb=_progress_cb,
                    resume_feedback_response=resume_feedback,
                )

                # If not waiting for feedback, done.
                hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
                blocker_registry = hitl_state.get("blocker_registry") if isinstance(hitl_state.get("blocker_registry"), dict) else {}
                waiting_projection = derive_waiting_feedback_projection(
                    blocker_registry=blocker_registry,
                    fallback_prompt_id=str(hitl_state.get("pending_feedback_prompt_id") or "").strip() or None,
                    fallback_decision_key=str(hitl_state.get("pending_feedback_decision_key") or "").strip().lower() or None,
                )
                # Also treat kernel-path waiting_human as a waiting-feedback signal.
                # derive_waiting_feedback_projection may miss this when the blocker_registry
                # has rows (from orient) but none are in waiting_feedback state yet.
                # Use state_pending_feedback_prompt_id which bypasses the registry projection.
                _direct_prompt_id = (
                    str(hitl_state.get("state_pending_feedback_prompt_id") or "").strip()
                    or str(hitl_state.get("pending_feedback_prompt_id") or "").strip()
                    or None
                )
                _is_waiting = waiting_projection.get("waiting_feedback") or (
                    result.status == "waiting_feedback" and bool(_direct_prompt_id)
                )
                if not _is_waiting:
                    return result

                prompt_id = (
                    str(waiting_projection.get("pending_feedback_prompt_id") or "").strip()
                    or _direct_prompt_id
                    or None
                )
                if not prompt_id:
                    return result  # Cannot resume without a prompt_id.

                # Emit the HITL event so hitl_watch can surface it to the agent.
                if _progress_cb is not None:
                    _pending_prompt = hitl_state.get("pending_feedback_prompt") if isinstance(hitl_state.get("pending_feedback_prompt"), dict) else {}
                    _pending_decision_key = (
                        str(waiting_projection.get("pending_feedback_decision_key") or "").strip()
                        or str(hitl_state.get("state_pending_feedback_decision_key") or "").strip()
                        or None
                    )
                    _progress_cb({
                        "event_type": "human_feedback_needed",
                        "run_id": viewer_run_id,
                        "prompt_id": prompt_id,
                        "decision_key": _pending_decision_key,
                        "message": _pending_prompt.get("line1") or f"Human feedback needed for: {_pending_decision_key}",
                        "choices": list(_pending_prompt.get("choices") or []),
                        "context": dict(_pending_prompt.get("context") or {}),
                        "phase": "human_feedback_needed",
                    })

                # Block-poll the feedback store until the tester injects a response.
                deadline = _time.time() + _FEEDBACK_POLL_TIMEOUT
                feedback_entry: dict[str, Any] | None = None
                while _time.time() < deadline:
                    feedback_entry = poll_feedback_response(run_id=viewer_run_id, prompt_id=prompt_id)
                    if feedback_entry is not None:
                        break
                    _time.sleep(_FEEDBACK_POLL_INTERVAL)

                if feedback_entry is None:
                    return result  # Timed out waiting for feedback.

                # Resume with the feedback injected via the kernel's HITL pre-phase.
                resume_decision_key = (
                    str(waiting_projection.get("pending_feedback_decision_key") or "").strip().lower()
                    or str(hitl_state.get("state_pending_feedback_decision_key") or "").strip().lower()
                    or str(hitl_state.get("pending_feedback_decision_key") or "").strip().lower()
                    or None
                )
                run_request = run_request.model_copy(update={
                    "resume_pending_feedback_prompt_id": prompt_id,
                    "resume_pending_feedback_decision_key": resume_decision_key,
                    "resume_blocker_registry": blocker_registry if blocker_registry else None,
                })
                resume_feedback = dict(feedback_entry)

            return result  # Max HITL resume rounds reached.

        return TranscriptEditModePolicy(runner=_ok_runner)

    def _runner(request: MissionRuntimeRequest, ledger: Any) -> Any:
        import time

        run_request = _build_run_request(request, ledger)
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


def infer_deed_ir_ref_from_ledger(ledger: Any) -> str | None:
    refs = getattr(ledger, "high_signal_artifact_refs", ())
    if not isinstance(refs, tuple):
        return None
    for candidate in reversed(refs):
        if not isinstance(candidate, str):
            continue
        text = candidate.strip()
        if not text:
            continue
        lower = text.lower()
        if ("ir" in lower or "graph" in lower) and "transcript" not in lower:
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


def persist_mission_trace_index(
    *,
    mission_request: MissionRuntimeRequest,
    ledger: Any,
    cycle_results: list[MissionRuntimeCycleResult],
) -> str | None:
    from .observability import build_mission_observation_from_runtime, build_mission_trace_index
    import json as _json
    try:
        observation = build_mission_observation_from_runtime(
            request=mission_request,
            ledger=ledger,
            cycle_results=cycle_results,
        )
        has_transitions = any(t.status == "applied" for t in observation.transition_history)
        if not has_transitions:
            return None
        trace_index = build_mission_trace_index(observation=observation)
        try:
            from config.paths import dossiers_artifacts_root
        except ModuleNotFoundError:
            from backend.config.paths import dossiers_artifacts_root  # type: ignore[no-redef]
        mission_id = str(getattr(mission_request, "mission_id", None) or "unknown").strip()
        dest = dossiers_artifacts_root() / "mission_traces" / f"mission_trace_{mission_id}.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(_json.dumps(trace_index, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(dest)
    except Exception:
        return None


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
        policies.append(build_deed_mode_policy_from_cli_inputs(deed_inputs, mission_request=mission_request))
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
