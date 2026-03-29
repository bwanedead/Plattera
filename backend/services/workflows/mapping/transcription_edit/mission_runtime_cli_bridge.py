from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_kernel.session import build_kernel_session_manager
from feature_graph.kernel_executor_composition import build_plattera_default_action_executor
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService

from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.hitl_watch import hitl_pending_path

from domains.mapping.transcript_edit.contracts import TranscriptEditAgentRunRequest
from domains.mapping.transcript_edit.hitl_feedback import (
    poll_feedback_response,
    viewer_run_id_from_request_prefix,
)
from domains.mapping.transcript_edit.mission_mode_adapter import TranscriptEditModeAdapter
from .mission_runtime_bridge import run_orchestration_kernel_transcript_loop
from domains.mapping.transcript_edit.state_projection import derive_waiting_feedback_projection

_PRACTICE_LEGALTEXT_DOSSIER_ID = "live-validation-practice-legaltext"
_PRACTICE_LEGALTEXT_SEED_FILENAME = "draft_legal_text_image_v2.json"
_TX_KNOWN_SCENARIOS: frozenset[str] = frozenset({"practice_legaltext"})


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


def resolve_tx_scenario(scenario_name: str) -> tuple[str | None, str | None]:
    if scenario_name not in _TX_KNOWN_SCENARIOS:
        return None, None
    if scenario_name == "practice_legaltext":
        return _PRACTICE_LEGALTEXT_DOSSIER_ID, _find_practice_legaltext_transcript()
    return None, None


def build_transcript_mode_adapter_from_cli_inputs(
    *,
    inputs: TranscriptModeCliInputs,
    mission_request: MissionRuntimeRequest,
):
    session_manager = build_kernel_session_manager(
        action_executor=build_plattera_default_action_executor(),
        persistence_service=RunArtifactPersistenceService(),
    )
    request_prefix = f"mission-{mission_request.mission_id}-tx"
    hitl_file = hitl_pending_path(request_prefix)

    def _progress_cb(event: dict[str, Any]) -> None:
        if not (isinstance(event, dict) and event.get("event_type") == "human_feedback_needed"):
            return
        try:
            import json as _json

            hitl_file.parent.mkdir(parents=True, exist_ok=True)
            hitl_file.write_text(_json.dumps(dict(event), ensure_ascii=False), encoding="utf-8")
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

    def _runner(request: MissionRuntimeRequest, ledger: Any) -> Any:
        import time as _time

        run_request = _build_run_request(request, ledger)
        viewer_run_id = viewer_run_id_from_request_prefix(request_prefix)
        resume_feedback: dict[str, Any] | None = None
        for _round in range(10):
            result = run_orchestration_kernel_transcript_loop(
                session_manager=session_manager,
                request=run_request,
                request_id_prefix=request_prefix,
                planner=None,
                progress_cb=_progress_cb,
                resume_feedback_response=resume_feedback,
            )

            hitl_state = result.runtime_hitl_state if isinstance(result.runtime_hitl_state, dict) else {}
            blocker_registry = (
                hitl_state.get("blocker_registry") if isinstance(hitl_state.get("blocker_registry"), dict) else {}
            )
            waiting_projection = derive_waiting_feedback_projection(
                blocker_registry=blocker_registry,
                fallback_prompt_id=str(hitl_state.get("pending_feedback_prompt_id") or "").strip() or None,
                fallback_decision_key=str(hitl_state.get("pending_feedback_decision_key") or "").strip().lower() or None,
            )
            direct_prompt_id = (
                str(hitl_state.get("state_pending_feedback_prompt_id") or "").strip()
                or str(hitl_state.get("pending_feedback_prompt_id") or "").strip()
                or None
            )
            is_waiting = waiting_projection.get("waiting_feedback") or (
                result.status == "waiting_feedback" and bool(direct_prompt_id)
            )
            if not is_waiting:
                return result

            prompt_id = str(waiting_projection.get("pending_feedback_prompt_id") or "").strip() or direct_prompt_id or None
            if not prompt_id:
                return result

            pending_prompt = (
                hitl_state.get("pending_feedback_prompt")
                if isinstance(hitl_state.get("pending_feedback_prompt"), dict)
                else {}
            )
            pending_decision_key = (
                str(waiting_projection.get("pending_feedback_decision_key") or "").strip()
                or str(hitl_state.get("state_pending_feedback_decision_key") or "").strip()
                or None
            )
            _progress_cb(
                {
                    "event_type": "human_feedback_needed",
                    "run_id": viewer_run_id,
                    "prompt_id": prompt_id,
                    "decision_key": pending_decision_key,
                    "message": pending_prompt.get("line1")
                    or f"Human feedback needed for: {pending_decision_key}",
                    "choices": list(pending_prompt.get("choices") or []),
                    "context": dict(pending_prompt.get("context") or {}),
                    "phase": "human_feedback_needed",
                }
            )

            deadline = _time.time() + 600
            feedback_entry: dict[str, Any] | None = None
            while _time.time() < deadline:
                feedback_entry = poll_feedback_response(run_id=viewer_run_id, prompt_id=prompt_id)
                if feedback_entry is not None:
                    break
                _time.sleep(2.0)
            if feedback_entry is None:
                return result

            resume_decision_key = (
                str(waiting_projection.get("pending_feedback_decision_key") or "").strip().lower()
                or str(hitl_state.get("state_pending_feedback_decision_key") or "").strip().lower()
                or str(hitl_state.get("pending_feedback_decision_key") or "").strip().lower()
                or None
            )
            run_request = run_request.model_copy(
                update={
                    "resume_pending_feedback_prompt_id": prompt_id,
                    "resume_pending_feedback_decision_key": resume_decision_key,
                    "resume_blocker_registry": blocker_registry if blocker_registry else None,
                }
            )
            resume_feedback = dict(feedback_entry)

        return result

    return TranscriptEditModeAdapter(runner=runner)


def infer_transcript_ref_from_ledger(ledger: Any) -> str | None:
    refs = getattr(ledger, "high_signal_artifact_refs", ())
    if not isinstance(refs, tuple):
        return None
    for candidate in reversed(refs):
        if not isinstance(candidate, str):
            continue
        text = candidate.strip()
        if text and "transcript" in text.lower():
            return text
    return None


def _find_practice_legaltext_transcript() -> str | None:
    try:
        from config.paths import dossiers_views_root
    except ModuleNotFoundError:
        from backend.config.paths import dossiers_views_root  # type: ignore[no-redef]
    try:
        dossier_dir = dossiers_views_root() / _PRACTICE_LEGALTEXT_DOSSIER_ID
        if not dossier_dir.exists():
            return None
        matches = sorted(dossier_dir.rglob(_PRACTICE_LEGALTEXT_SEED_FILENAME))
        if matches:
            return str(matches[-1])
        raw_files = sorted(dossier_dir.rglob("raw/*.json"), key=lambda path: path.stat().st_mtime)
        if raw_files:
            return str(raw_files[-1])
    except Exception:
        pass
    return None
