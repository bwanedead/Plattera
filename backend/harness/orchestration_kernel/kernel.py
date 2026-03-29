from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from agent_kernel.models import KernelStepRequest, StepExecutionState
from agent_kernel.session import KernelSessionManager

from ..mission_state import MissionState, ResolutionState, new_mission_state, new_resolution_state
from ..terminal_taxonomy import TerminalClass
from .contracts import ActionPlan
from .trace_collector import KernelTraceCollector

_LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class SharedStateProjection:
    mission_state: MissionState
    resolution_state: ResolutionState
    latest_refs: dict[str, Any] = field(default_factory=dict)
    active_item_id: str | None = None


@dataclass(frozen=True)
class TerminalEvaluation:
    terminal_class: TerminalClass
    reason_code: str


@dataclass
class LoopMemoryState:
    """Kernel-owned loop memory and transport posture."""

    iterations: int = 0
    latest_refs: dict[str, Any] = field(default_factory=dict)

    mission_state: MissionState = field(
        default_factory=lambda: new_mission_state(
            mission_id="unknown_mission",
            loop_family="orchestration_kernel",
            resolution_state=new_resolution_state(),
        )
    )
    resolution_state: ResolutionState = field(default_factory=new_resolution_state)
    active_item_id: str | None = None

    hitl_state: str = "no_prompt"
    pending_feedback_prompt_id: str | None = None
    pending_feedback_response: dict[str, Any] | None = None

    llm_contact_count: int = 0
    prompt_event_count: int = 0
    last_prompt_event_id: str | None = None
    last_prompt_event_surface: str | None = None

    def register_llm_contact(self) -> None:
        self.llm_contact_count += 1

    def register_prompt_event(self, *, prompt_event_id: str | None, surface: str | None) -> None:
        self.prompt_event_count += 1
        if isinstance(prompt_event_id, str) and prompt_event_id.strip():
            self.last_prompt_event_id = prompt_event_id.strip()
        if isinstance(surface, str) and surface.strip():
            self.last_prompt_event_surface = surface.strip()


@dataclass(frozen=True)
class OrchestratorContext:
    session_manager: KernelSessionManager
    session_id: str
    loop_memory: LoopMemoryState
    request_id_prefix: str
    dossier_id: str | None = None


@dataclass(frozen=True)
class KernelLoopResult:
    terminal_class: TerminalClass
    reason_code: str
    iterations: int
    session_id: str
    run_artifact_ref: str | None
    latest_refs: dict[str, Any] = field(default_factory=dict)
    runtime_state: dict[str, Any] = field(default_factory=dict)
    trace_events: list[dict[str, Any]] = field(default_factory=list)

    @property
    def domain_runtime_state(self) -> dict[str, Any]:
        return self.runtime_state


def run_orchestration_kernel_loop(
    *,
    orchestration_pack: Any,
    session_manager: KernelSessionManager,
    session_id: str,
    run_artifact_ref: str | None,
    request_id_prefix: str,
    dossier_id: str | None,
    max_iterations: int,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    resume_hitl_response: dict[str, Any] | None = None,
) -> KernelLoopResult:
    """Drive a minimal generic mission loop skeleton."""
    loop_memory = LoopMemoryState()
    if isinstance(resume_hitl_response, dict) and resume_hitl_response:
        loop_memory.hitl_state = "answered_unintegrated"
        loop_memory.pending_feedback_response = resume_hitl_response
        _LOG.info("KERNEL resume_hitl_preseeded ► request_id=%s", request_id_prefix)

    context = OrchestratorContext(
        session_manager=session_manager,
        session_id=session_id,
        loop_memory=loop_memory,
        request_id_prefix=request_id_prefix,
        dossier_id=dossier_id,
    )

    tracer = KernelTraceCollector(session_id=session_id, request_id=request_id_prefix)
    tracer.emit_request_start(
        dossier_id=dossier_id,
        max_iterations=max_iterations,
        run_artifact_ref=run_artifact_ref,
    )

    def _identity_trace_cb(info: dict[str, Any]) -> None:
        prompt_event = info.get("prompt_event")
        if isinstance(prompt_event, dict):
            metadata = prompt_event.get("metadata") if isinstance(prompt_event.get("metadata"), dict) else {}
            tracer.emit_prompt_event(
                iteration=None,
                prompt_event=prompt_event,
                surface=str(metadata.get("surface") or info.get("surface") or ""),
                domain=str(metadata.get("domain") or info.get("domain") or ""),
                model=str(metadata.get("model") or info.get("model") or ""),
            )
            loop_memory.register_prompt_event(
                prompt_event_id=str(metadata.get("prompt_event_id") or ""),
                surface=str(metadata.get("surface") or info.get("surface") or ""),
            )
            return
        tracer.emit_llm_call_identity(
            iteration=None,
            surface=str(info.get("surface") or ""),
            domain=str(info.get("domain") or ""),
            inheritance_mode=str(info.get("inheritance_mode") or ""),
            constitution_version=str(info.get("constitution_version") or ""),
            run_link_id=str(info.get("run_link_id") or ""),
            model=str(info.get("model") or ""),
        )
        loop_memory.register_llm_contact()

    if hasattr(orchestration_pack, "wire_identity_trace_cb"):
        orchestration_pack.wire_identity_trace_cb(_identity_trace_cb)  # type: ignore[attr-defined]
    if hasattr(session_manager, "wire_identity_trace_cb"):
        session_manager.wire_identity_trace_cb(_identity_trace_cb)  # type: ignore[attr-defined]

    _call_optional(orchestration_pack, "initialize", context)

    for iterations in range(1, max_iterations + 1):
        loop_memory.iterations = iterations
        tracer.emit_iteration_start(iteration=iterations, hitl_state=loop_memory.hitl_state)

        if loop_memory.hitl_state == "waiting" and loop_memory.pending_feedback_response is None:
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        projection = _coerce_projection(_call_optional(orchestration_pack, "sync", context))
        if projection is not None:
            loop_memory.mission_state = projection.mission_state
            loop_memory.resolution_state = projection.resolution_state
            if projection.latest_refs:
                loop_memory.latest_refs = dict(projection.latest_refs)
            loop_memory.active_item_id = (
                projection.active_item_id
                or projection.resolution_state.active_item_id
                or loop_memory.active_item_id
            )

        terminal = _coerce_terminal_evaluation(_call_optional(orchestration_pack, "evaluate_terminal", context, projection))
        if terminal is not None:
            return _make_result(
                loop_memory=loop_memory,
                terminal_class=terminal.terminal_class,
                reason_code=terminal.reason_code,
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        action_plan = _coerce_action_plan(_call_optional(orchestration_pack, "choose_action", context, projection))
        if action_plan is None:
            continue

        if action_plan.wait_for_human:
            loop_memory.hitl_state = "waiting"
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="waiting_human",
                reason_code="waiting_human_feedback",
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        if action_plan.complete_run:
            return _make_result(
                loop_memory=loop_memory,
                terminal_class="completed",
                reason_code=str(action_plan.rationale or "complete_run"),
                iterations=iterations,
                session_id=session_id,
                run_artifact_ref=run_artifact_ref,
                tracer=tracer,
            )

        step_request = _coerce_step_request(action_plan, session_id=session_id)
        if step_request is not None and not action_plan.skip_execution:
            step_result = session_manager.step(step_request)
            if step_result.execution_state != StepExecutionState.EXECUTED:
                refusal = step_result.refusal
                reason = refusal.reason_code if refusal is not None else "step_execution_refused"
                retryable = refusal.retryable if refusal is not None else False
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(step_request.action_type),
                    execution_state="refused",
                    reason_code=reason,
                    retryable=retryable,
                    refs_delta=None,
                )
                is_retryable = (
                    refusal is not None
                    and refusal.retryable
                    and not refusal.blocked_by_budget
                    and not refusal.blocked_by_invariant
                )
                if not is_retryable:
                    return _make_result(
                        loop_memory=loop_memory,
                        terminal_class="failed",
                        reason_code=reason,
                        iterations=iterations,
                        session_id=session_id,
                        run_artifact_ref=run_artifact_ref,
                        tracer=tracer,
                    )
                if step_result.dashboard is not None:
                    loop_memory.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
            else:
                if step_result.dashboard is not None:
                    loop_memory.latest_refs = step_result.dashboard.latest_refs.model_dump(mode="json")
                tracer.emit_execution_result(
                    iteration=iterations,
                    action_type=str(step_request.action_type),
                    execution_state="executed",
                    reason_code=None,
                    retryable=None,
                    refs_delta=loop_memory.latest_refs,
                )

    return _make_result(
        loop_memory=loop_memory,
        terminal_class="exhausted",
        reason_code="max_iterations_reached",
        iterations=loop_memory.iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        tracer=tracer,
    )


def _call_optional(obj: Any, name: str, *args: Any, **kwargs: Any) -> Any:
    fn = getattr(obj, name, None)
    if not callable(fn):
        return None
    return fn(*args, **kwargs)


def _coerce_projection(value: Any) -> SharedStateProjection | None:
    if value is None:
        return None
    if isinstance(value, SharedStateProjection):
        return value
    if isinstance(value, dict):
        mission_state = value.get("mission_state")
        resolution_state = value.get("resolution_state")
        if not isinstance(mission_state, MissionState) or not isinstance(resolution_state, ResolutionState):
            return None
        return SharedStateProjection(
            mission_state=mission_state,
            resolution_state=resolution_state,
            latest_refs=dict(value.get("latest_refs") or {}),
            active_item_id=str(value.get("active_item_id") or "").strip() or None,
        )
    mission_state = getattr(value, "mission_state", None)
    resolution_state = getattr(value, "resolution_state", None)
    if not isinstance(mission_state, MissionState) or not isinstance(resolution_state, ResolutionState):
        return None
    latest_refs = getattr(value, "latest_refs", {})
    active_item_id = getattr(value, "active_item_id", None)
    return SharedStateProjection(
        mission_state=mission_state,
        resolution_state=resolution_state,
        latest_refs=dict(latest_refs) if isinstance(latest_refs, dict) else {},
        active_item_id=str(active_item_id or "").strip() or None,
    )


def _coerce_action_plan(value: Any) -> ActionPlan | None:
    if value is None:
        return None
    if isinstance(value, ActionPlan):
        return value
    if isinstance(value, dict):
        return ActionPlan(
            action_type=str(value.get("action_type") or "").strip() or None,
            action_inputs=dict(value.get("action_inputs") or {}),
            idempotency_key=str(value.get("idempotency_key") or ""),
            skip_execution=bool(value.get("skip_execution", False)),
            wait_for_human=bool(value.get("wait_for_human", False)),
            complete_run=bool(value.get("complete_run", False)),
            rationale=str(value.get("rationale") or "").strip() or None,
        )
    action_inputs = getattr(value, "action_inputs", None)
    return ActionPlan(
        action_type=str(getattr(value, "action_type", "") or "").strip() or None,
        action_inputs=action_inputs if isinstance(action_inputs, dict) else {},
        idempotency_key=str(getattr(value, "idempotency_key", "") or ""),
        skip_execution=bool(getattr(value, "skip_execution", False)),
        wait_for_human=bool(getattr(value, "wait_for_human", False)),
        complete_run=bool(getattr(value, "complete_run", False)),
        rationale=str(getattr(value, "rationale", "") or "").strip() or None,
    )


def _coerce_step_request(value: Any, *, session_id: str) -> KernelStepRequest | None:
    if value is None:
        return None
    if isinstance(value, KernelStepRequest):
        return value
    if isinstance(value, ActionPlan):
        if value.action_type is None:
            return None
        return KernelStepRequest(
            session_id=session_id,
            action_type=value.action_type,
            inputs=dict(value.action_inputs),
            idempotency_key=value.idempotency_key,
        )
    if isinstance(value, dict):
        action_type = value.get("action_type")
        inputs = value.get("inputs")
        if action_type is None:
            return None
        return KernelStepRequest(
            session_id=str(value.get("session_id") or session_id),
            action_type=action_type,
            inputs=inputs if isinstance(inputs, dict) else {},
            idempotency_key=str(value.get("idempotency_key") or ""),
        )
    action_type = getattr(value, "action_type", None)
    inputs = getattr(value, "inputs", None)
    if action_type is None:
        return None
    return KernelStepRequest(
        session_id=str(getattr(value, "session_id", None) or session_id),
        action_type=action_type,
        inputs=inputs if isinstance(inputs, dict) else {},
        idempotency_key=str(getattr(value, "idempotency_key", "") or ""),
    )


def _coerce_terminal_evaluation(value: Any) -> TerminalEvaluation | None:
    if value is None:
        return None
    if isinstance(value, TerminalEvaluation):
        return value
    if isinstance(value, dict):
        terminal_class = value.get("terminal_class")
        reason_code = str(value.get("reason_code") or "").strip()
        if terminal_class is None or not reason_code:
            return None
        return TerminalEvaluation(terminal_class=terminal_class, reason_code=reason_code)
    terminal_class = getattr(value, "terminal_class", None)
    reason_code = str(getattr(value, "reason_code", "") or "").strip()
    if terminal_class is None or not reason_code:
        return None
    return TerminalEvaluation(terminal_class=terminal_class, reason_code=reason_code)


def _make_result(
    *,
    loop_memory: LoopMemoryState,
    terminal_class: TerminalClass,
    reason_code: str,
    iterations: int,
    session_id: str,
    run_artifact_ref: str | None,
    tracer: KernelTraceCollector,
) -> KernelLoopResult:
    tracer.emit_terminal(
        iteration=iterations,
        terminal_class=terminal_class,
        reason_code=reason_code,
    )
    runtime_state = {
        "hitl_state": loop_memory.hitl_state,
        "pending_feedback_prompt_id": loop_memory.pending_feedback_prompt_id,
        "active_item_id": loop_memory.active_item_id,
        "llm_contact_count": loop_memory.llm_contact_count,
        "prompt_event_count": loop_memory.prompt_event_count,
        "last_prompt_event_id": loop_memory.last_prompt_event_id,
        "last_prompt_event_surface": loop_memory.last_prompt_event_surface,
        "mission_state": loop_memory.mission_state,
        "resolution_state": loop_memory.resolution_state,
    }
    return KernelLoopResult(
        terminal_class=terminal_class,
        reason_code=reason_code,
        iterations=iterations,
        session_id=session_id,
        run_artifact_ref=run_artifact_ref,
        latest_refs=dict(loop_memory.latest_refs),
        runtime_state=runtime_state,
        trace_events=tracer.build_raw_events(),
    )
