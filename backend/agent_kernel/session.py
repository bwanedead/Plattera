"""Step-driven kernel session manager (start_session + step).

**Canonical Agent Kernel integration** for missions: use ``KernelSessionManager`` from the
``agent_kernel`` package. The JSON ``run_kernel`` loop in ``kernel.py`` is a compatibility surface
(see ``COMPATIBILITY.md``) — not the primary development path.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from time import time
from typing import Any, Callable, Protocol
from uuid import uuid4

from config.paths import agent_kernel_artifacts_root

from .actions import ActionExecutor, ActionExecutorDeps
from .claimability import ClaimabilityPolicy, evaluate_claimability
from .dashboard_refs import build_latest_refs_map, build_latest_validate_ref
from .harness_action_ids import ActionType, HarnessAction, canonical_action_id
from .models import (
    KernelClaimabilityStatus,
    KernelDashboard,
    KernelFailureClassification,
    KernelGapSummary,
    KernelLatestRefs,
    KernelNoProgressRisk,
    KernelRefusal,
    KernelSessionStartRequest,
    KernelSessionStartResult,
    KernelStepRequest,
    KernelStepResult,
    StepExecutionState,
    StopReason,
    TerminalOutcome,
    TerminalOutcomeKind,
)
from .run_artifact import ArtifactRef, RunArtifact, StepRecord
_MAX_INPUT_BYTES = 4096
_MAX_INITIAL_GRAPH_JSON_BYTES = 262144
_MAX_DASHBOARD_LIST = 10
_MAX_MISSING_CLAIMABILITY = 20
class SessionPersistence(Protocol):
    """Persistence contract needed by the step-driven kernel session manager."""

    def save_run_artifact(self, run_artifact: RunArtifact) -> dict[str, object]: ...

    def get_run_artifact(self, request_id: str, run_id: str) -> RunArtifact | None: ...


class KernelSessionManager:
    """Primary step-driven kernel interface: start_session + step."""

    def __init__(
        self,
        *,
        action_executor: ActionExecutor | None = None,
        default_action_executor_factory: Callable[[], ActionExecutor] | None = None,
        claimability_policy: ClaimabilityPolicy | None = None,
        persistence_service: SessionPersistence | None = None,
    ) -> None:
        self._action_executor = action_executor or (
            default_action_executor_factory() if default_action_executor_factory is not None else ActionExecutor()
        )
        self._claimability_policy = claimability_policy
        self._persistence_service = persistence_service

    def wire_identity_trace_cb(self, cb: Callable[[dict[str, Any]], None] | None) -> None:
        """Wire prompt/identity tracing through the configured action executor."""
        self._action_executor.wire_identity_trace_cb(cb)

    def start_session(self, request: KernelSessionStartRequest) -> KernelSessionStartResult:
        missing_inputs = _validate_bootstrap_inputs(request)
        if missing_inputs:
            refusal = KernelRefusal(
                reason_code="bootstrap_missing_inputs",
                missing_inputs=missing_inputs,
                retryable=True,
            )
            dashboard = _build_empty_dashboard(refusal=refusal, semantic_ready=None)
            return KernelSessionStartResult(
                tool_menu=[],
                dashboard=dashboard,
                budgets_remaining=dashboard.budgets_remaining,
                refusal=refusal,
            )

        bootstrap_refusal = _validate_initial_graph_json(request.initial_graph_json)
        if bootstrap_refusal is not None:
            dashboard = _build_empty_dashboard(refusal=bootstrap_refusal, semantic_ready=None)
            return KernelSessionStartResult(
                tool_menu=[],
                dashboard=dashboard,
                budgets_remaining=dashboard.budgets_remaining,
                refusal=bootstrap_refusal,
            )

        run_id = f"{request.request_id}-session-{int(time())}"
        session_id = request.session_id or _compose_session_id(request.request_id, run_id)
        run_artifact = RunArtifact(
            run_id=run_id,
            request_id=request.request_id,
            session_id=session_id,
            requires_global_placement=request.goal.requires_global_placement,
            render_required=request.goal.render_required,
            created_at_epoch_seconds=int(time()),
            session_budgets=request.budgets.model_dump(mode="json"),
            ir_artifact_ref=(
                ArtifactRef(artifact_path=request.initial_ir_ref)
                if request.initial_ir_ref is not None
                else None
            ),
        )
        if run_artifact.ir_artifact_ref is None and request.initial_graph_json is not None:
            run_artifact.ir_artifact_ref = _persist_bootstrap_ir_graph(
                request_id=request.request_id,
                run_id=run_id,
                graph=request.initial_graph_json,
            )

        run_artifact_ref = None
        if self._persistence_service is not None:
            persisted = self._persistence_service.save_run_artifact(run_artifact)
            run_artifact_ref = str(persisted.get("path"))

        dashboard = _build_dashboard(
            run_artifact=run_artifact,
            budgets=run_artifact.session_budgets,
            claimability_policy=self._claimability_policy,
            semantic_ready=None,
            last_refusal=None,
            failure_reason=None,
            failure_code=None,
        )
        return KernelSessionStartResult(
            session_id=session_id,
            run_id=run_id,
            run_artifact_ref=run_artifact_ref,
            tool_menu=_tool_menu(self._action_executor),
            dashboard=dashboard,
            budgets_remaining=dashboard.budgets_remaining,
            refusal=None,
        )

    def step(self, request: KernelStepRequest) -> KernelStepResult:
        """Execute one step. **Idempotency** is keyed per ``idempotency_key`` on the **loaded** run artifact.

        Each ``start_session`` persists a new ``RunArtifact`` (new internal ``run_id``); the ledger does not
        carry across unrelated sessions. Retries/resumes within the **same** session reuse the same ledger.
        """
        run_artifact = self._load_run_artifact(request.session_id)
        if run_artifact is None:
            refusal = KernelRefusal(
                reason_code="session_not_found",
                missing_inputs=["session_id"],
                retryable=False,
            )
            return KernelStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=StepExecutionState.REFUSED,
                refusal=refusal,
                dashboard=_build_empty_dashboard(refusal=refusal, semantic_ready=request.semantic_ready),
            )

        fingerprint = _fingerprint_step_request(request)
        existing = run_artifact.idempotency_ledger.get(request.idempotency_key)
        if existing is not None:
            existing_fp = str(existing.get("request_fingerprint", ""))
            if existing_fp != fingerprint:
                refusal = KernelRefusal(
                    reason_code="idempotency_key_payload_mismatch",
                    retryable=False,
                    blocked_by_invariant=True,
                )
                dashboard = _build_dashboard(
                    run_artifact=run_artifact,
                    budgets=_extract_budgets(existing),
                    claimability_policy=self._claimability_policy,
                    semantic_ready=request.semantic_ready,
                    last_refusal=refusal,
                    failure_reason=StopReason.INTERNAL_ERROR,
                    failure_code=refusal.reason_code,
                )
                return KernelStepResult(
                    session_id=request.session_id,
                    idempotency_key=request.idempotency_key,
                    execution_state=StepExecutionState.REFUSED,
                    refusal=refusal,
                    dashboard=dashboard,
                )

            deduped_step = _lookup_step(run_artifact, str(existing.get("step_id", "")))
            refusal = _coerce_refusal(existing.get("refusal"))
            dashboard = _build_dashboard(
                run_artifact=run_artifact,
                budgets=_extract_budgets(existing),
                claimability_policy=self._claimability_policy,
                semantic_ready=request.semantic_ready,
                last_refusal=refusal,
                failure_reason=None,
                failure_code=None,
            )
            return KernelStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=StepExecutionState.DEDUPED,
                step_record=deduped_step.model_dump(mode="json") if deduped_step is not None else None,
                refusal=refusal,
                dashboard=dashboard,
                terminal=_coerce_terminal(existing.get("terminal")),
            )

        budgets = _extract_or_default_budgets(run_artifact)
        budget_refusal, budget_terminal = _check_budget_limits(run_artifact, budgets)
        if budget_refusal is not None:
            result = self._build_refusal_result(
                run_artifact=run_artifact,
                request=request,
                refusal=budget_refusal,
                budgets=budgets,
                terminal=budget_terminal,
            )
            self._record_idempotency_entry(
                run_artifact=run_artifact,
                request=request,
                fingerprint=fingerprint,
                step=None,
                refusal=budget_refusal,
                terminal=budget_terminal,
                budgets=budgets,
            )
            self._persist(run_artifact)
            return result

        invariant_refusal = _validate_step_inputs(request.inputs)
        if invariant_refusal is not None:
            result = self._build_refusal_result(
                run_artifact=run_artifact,
                request=request,
                refusal=invariant_refusal,
                budgets=budgets,
                terminal=None,
            )
            self._record_idempotency_entry(
                run_artifact=run_artifact,
                request=request,
                fingerprint=fingerprint,
                step=None,
                refusal=invariant_refusal,
                terminal=None,
                budgets=budgets,
            )
            self._persist(run_artifact)
            return result

        if canonical_action_id(request.action_type) == ActionType.DECLARE_DONE.value:
            return self._handle_declare_done(
                run_artifact=run_artifact,
                request=request,
                fingerprint=fingerprint,
                budgets=budgets,
            )

        step_id = f"step-{len(run_artifact.steps) + 1:03d}"
        step = self._action_executor.execute(
            step_id=step_id,
            action=request.action_type,
            inputs=request.inputs,
        )
        run_artifact.steps.append(step)
        tool_refusal = _extract_tool_refusal(step)
        if tool_refusal is not None:
            self._record_idempotency_entry(
                run_artifact=run_artifact,
                request=request,
                fingerprint=fingerprint,
                step=step,
                refusal=tool_refusal,
                terminal=None,
                budgets=budgets,
            )
            self._persist(run_artifact)
            dashboard = _build_dashboard(
                run_artifact=run_artifact,
                budgets=budgets,
                claimability_policy=self._claimability_policy,
                semantic_ready=request.semantic_ready,
                last_refusal=tool_refusal,
                failure_reason=None,
                failure_code=tool_refusal.reason_code,
            )
            return KernelStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=StepExecutionState.REFUSED,
                step_record=step.model_dump(mode="json"),
                refusal=tool_refusal,
                dashboard=dashboard,
            )
        _update_latest_refs(run_artifact, step, action_executor=self._action_executor)
        self._record_idempotency_entry(
            run_artifact=run_artifact,
            request=request,
            fingerprint=fingerprint,
            step=step,
            refusal=None,
            terminal=None,
            budgets=budgets,
        )
        self._persist(run_artifact)
        dashboard = _build_dashboard(
            run_artifact=run_artifact,
            budgets=budgets,
            claimability_policy=self._claimability_policy,
            semantic_ready=request.semantic_ready,
            last_refusal=None,
            failure_reason=None,
            failure_code=None,
        )
        return KernelStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=StepExecutionState.EXECUTED,
            step_record=step.model_dump(mode="json"),
            dashboard=dashboard,
        )

    def _handle_declare_done(
        self,
        *,
        run_artifact: RunArtifact,
        request: KernelStepRequest,
        fingerprint: str,
        budgets: dict[str, int],
    ) -> KernelStepResult:
        claimable_ready, missing = evaluate_claimability(self._claimability_policy, run_artifact)
        step_id = f"step-{len(run_artifact.steps) + 1:03d}"
        if not claimable_ready:
            refusal = KernelRefusal(
                reason_code="declare_done_claimability_missing",
                missing_inputs=missing[:_MAX_MISSING_CLAIMABILITY],
                retryable=True,
            )
            step = StepRecord(
                step_id=step_id,
                action=ActionType.DECLARE_DONE.value,
                inputs=request.inputs,
                reason_codes=["declare_done_refused"],
                outputs_inline={"missing_claimability": refusal.missing_inputs},
            )
            run_artifact.steps.append(step)
            self._record_idempotency_entry(
                run_artifact=run_artifact,
                request=request,
                fingerprint=fingerprint,
                step=step,
                refusal=refusal,
                terminal=None,
                budgets=budgets,
            )
            self._persist(run_artifact)
            dashboard = _build_dashboard(
                run_artifact=run_artifact,
                budgets=budgets,
                claimability_policy=self._claimability_policy,
                semantic_ready=request.semantic_ready,
                last_refusal=refusal,
                failure_reason=None,
                failure_code=refusal.reason_code,
            )
            return KernelStepResult(
                session_id=request.session_id,
                idempotency_key=request.idempotency_key,
                execution_state=StepExecutionState.REFUSED,
                step_record=step.model_dump(mode="json"),
                refusal=refusal,
                dashboard=dashboard,
            )

        step = StepRecord(
            step_id=step_id,
            action=ActionType.DECLARE_DONE.value,
            inputs=request.inputs,
            reason_codes=["declare_done_accepted"],
        )
        run_artifact.steps.append(step)
        terminal = TerminalOutcome(
            terminal_outcome=TerminalOutcomeKind.SUCCESS,
            stop_reason=StopReason.COMPLETED,
            success=True,
            reason_code="declare_done_accepted",
        )
        self._record_idempotency_entry(
            run_artifact=run_artifact,
            request=request,
            fingerprint=fingerprint,
            step=step,
            refusal=None,
            terminal=terminal,
            budgets=budgets,
        )
        _run_terminal_success_hooks(run_artifact, action_executor=self._action_executor)
        self._persist(run_artifact)
        dashboard = _build_dashboard(
            run_artifact=run_artifact,
            budgets=budgets,
            claimability_policy=self._claimability_policy,
            semantic_ready=request.semantic_ready,
            last_refusal=None,
            failure_reason=StopReason.COMPLETED,
            failure_code="declare_done_accepted",
        )
        return KernelStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=StepExecutionState.EXECUTED,
            step_record=step.model_dump(mode="json"),
            dashboard=dashboard,
            terminal=terminal,
        )

    def _build_refusal_result(
        self,
        *,
        run_artifact: RunArtifact,
        request: KernelStepRequest,
        refusal: KernelRefusal,
        budgets: dict[str, int],
        terminal: TerminalOutcome | None,
    ) -> KernelStepResult:
        dashboard = _build_dashboard(
            run_artifact=run_artifact,
            budgets=budgets,
            claimability_policy=self._claimability_policy,
            semantic_ready=request.semantic_ready,
            last_refusal=refusal,
            failure_reason=(terminal.stop_reason if terminal is not None else None),
            failure_code=(terminal.reason_code if terminal is not None else refusal.reason_code),
        )
        return KernelStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=StepExecutionState.REFUSED,
            refusal=refusal,
            dashboard=dashboard,
            terminal=terminal,
        )

    def _record_idempotency_entry(
        self,
        *,
        run_artifact: RunArtifact,
        request: KernelStepRequest,
        fingerprint: str,
        step: StepRecord | None,
        refusal: KernelRefusal | None,
        terminal: TerminalOutcome | None,
        budgets: dict[str, int],
    ) -> None:
        run_artifact.idempotency_ledger[request.idempotency_key] = {
            "request_fingerprint": fingerprint,
            "step_id": step.step_id if step is not None else None,
            "refusal": refusal.model_dump(mode="json") if refusal is not None else None,
            "terminal": terminal.model_dump(mode="json") if terminal is not None else None,
            "budgets": budgets,
        }

    def _load_run_artifact(self, session_id: str) -> RunArtifact | None:
        if self._persistence_service is None:
            return None
        request_id, run_id = _parse_session_id(session_id)
        if request_id is None or run_id is None:
            return None
        return self._persistence_service.get_run_artifact(request_id=request_id, run_id=run_id)

    def _persist(self, run_artifact: RunArtifact) -> None:
        if self._persistence_service is None:
            return
        self._persistence_service.save_run_artifact(run_artifact)


def build_kernel_session_manager(
    *,
    action_executor: ActionExecutor | None = None,
    default_action_executor_factory: Callable[[], ActionExecutor] | None = None,
    claimability_policy: ClaimabilityPolicy | None = None,
    persistence_service: SessionPersistence | None = None,
) -> KernelSessionManager:
    """Explicit runtime composition seam for shared kernel session hosts."""
    return KernelSessionManager(
        action_executor=action_executor,
        default_action_executor_factory=default_action_executor_factory,
        claimability_policy=claimability_policy,
        persistence_service=persistence_service,
    )


def _validate_bootstrap_inputs(request: KernelSessionStartRequest) -> list[str]:
    if request.initial_ir_ref is not None:
        return []
    if request.initial_graph_json is not None:
        return []
    if request.dossier_id and request.source_entry_ref:
        return []
    missing = []
    if not request.dossier_id:
        missing.append("dossier_id")
    if not request.source_entry_ref:
        missing.append("source_entry_ref")
    missing.append("initial_ir_ref_or_initial_graph_json")
    return missing


def _validate_initial_graph_json(initial_graph_json: dict[str, object] | None) -> KernelRefusal | None:
    if initial_graph_json is None:
        return None
    payload = json.dumps(initial_graph_json, sort_keys=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) <= _MAX_INITIAL_GRAPH_JSON_BYTES:
        return None
    return KernelRefusal(
        reason_code="bootstrap_graph_payload_too_large",
        retryable=False,
        blocked_by_invariant=True,
    )


def _compose_session_id(request_id: str, run_id: str) -> str:
    return f"{request_id}::{run_id}"


def _parse_session_id(session_id: str) -> tuple[str | None, str | None]:
    parts = session_id.rsplit("::", maxsplit=1)
    if len(parts) != 2:
        return None, None
    return parts[0], parts[1]


def _fingerprint_step_request(request: KernelStepRequest) -> str:
    canonical = json.dumps(
        {
            "action_type": request.action_type,
            "inputs": request.inputs,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_step_inputs(inputs: dict[str, object]) -> KernelRefusal | None:
    payload = json.dumps(inputs, sort_keys=True, separators=(",", ":"))
    if len(payload.encode("utf-8")) > _MAX_INPUT_BYTES:
        return KernelRefusal(
            reason_code="inputs_payload_too_large",
            retryable=False,
            blocked_by_invariant=True,
        )
    if _contains_large_geometry(inputs):
        return KernelRefusal(
            reason_code="inputs_include_large_geometry_blob",
            retryable=False,
            blocked_by_invariant=True,
        )
    return None


def _contains_large_geometry(value: object, parent_key: str = "") -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in {"geometry", "coordinates", "rings", "vertices", "polygon"}:
                if isinstance(nested, list) and len(nested) > 64:
                    return True
            if _contains_large_geometry(nested, key_lower):
                return True
        return False
    if isinstance(value, list):
        if parent_key in {"geometry", "coordinates", "rings", "vertices", "polygon"} and len(value) > 64:
            return True
        for nested in value:
            if _contains_large_geometry(nested, parent_key):
                return True
    return False


def _check_budget_limits(
    run_artifact: RunArtifact,
    budgets: dict[str, int],
) -> tuple[KernelRefusal | None, TerminalOutcome | None]:
    steps_used = len(run_artifact.steps)
    retrieval_calls = sum(
        1 for step in run_artifact.steps if canonical_action_id(step.action) == ActionType.RETRIEVE_EVIDENCE.value
    )
    semantic_calls = sum(
        1
        for step in run_artifact.steps
        if canonical_action_id(step.action) == ActionType.RETRIEVE_EVIDENCE.value
        and bool(step.inputs.get("semantic", False))
    )
    patch_calls = sum(
        1 for step in run_artifact.steps if canonical_action_id(step.action) == ActionType.PROPOSE_PATCH.value
    )
    elapsed_seconds = max(0, int(time()) - int(run_artifact.created_at_epoch_seconds or int(time())))

    checks = (
        ("budget_steps_exceeded", steps_used >= int(budgets.get("max_steps", 0))),
        ("budget_wall_time_exceeded", elapsed_seconds >= int(budgets.get("max_wall_time_seconds", 0))),
        ("budget_retrieval_calls_exceeded", retrieval_calls >= int(budgets.get("max_retrieval_calls", 0))),
        ("budget_semantic_calls_exceeded", semantic_calls >= int(budgets.get("max_semantic_calls", 0))),
        ("budget_patch_calls_exceeded", patch_calls >= int(budgets.get("max_patch_calls", 0))),
    )
    for reason_code, exceeded in checks:
        if not exceeded:
            continue
        refusal = KernelRefusal(
            reason_code=reason_code,
            retryable=False,
            blocked_by_budget=True,
        )
        terminal = TerminalOutcome(
            terminal_outcome=TerminalOutcomeKind.FAILED,
            stop_reason=StopReason.BUDGET_EXCEEDED,
            success=False,
            reason_code=reason_code,
        )
        return refusal, terminal
    return None, None


def _dashboard_artifact_ref_map(run_artifact: RunArtifact) -> dict[str, dict[str, object]]:
    return build_latest_refs_map(run_artifact)


def _build_dashboard(
    *,
    run_artifact: RunArtifact,
    budgets: dict[str, int],
    claimability_policy: ClaimabilityPolicy | None,
    semantic_ready: bool | None,
    last_refusal: KernelRefusal | None,
    failure_reason: StopReason | None,
    failure_code: str | None,
) -> KernelDashboard:
    latest_refs = KernelLatestRefs(artifact_refs=_dashboard_artifact_ref_map(run_artifact))

    gap_counts: dict[str, int] = {}
    for step in run_artifact.steps[-20:]:
        for code in step.reason_codes:
            gap_counts[code] = gap_counts.get(code, 0) + 1
    top_codes = sorted(gap_counts.keys(), key=lambda code: (-gap_counts[code], code))[:_MAX_DASHBOARD_LIST]

    claimable_ready, missing_claimability = evaluate_claimability(claimability_policy, run_artifact)
    budgets_remaining = _compute_budgets_remaining(run_artifact, budgets)
    return KernelDashboard(
        latest_refs=latest_refs,
        gap_summary=KernelGapSummary(
            top_gap_kinds=top_codes,
            gap_counts_by_kind={code: gap_counts[code] for code in top_codes},
            top_reason_codes=top_codes,
        ),
        claimability=KernelClaimabilityStatus(
            claimable_ready=claimable_ready,
            missing_claimability=missing_claimability[:_MAX_MISSING_CLAIMABILITY],
        ),
        semantic_ready=semantic_ready,
        budgets_remaining=budgets_remaining,
        failure_classification=KernelFailureClassification(
            stop_reason=failure_reason,
            reason_code=failure_code,
        ),
        no_progress_risk=KernelNoProgressRisk(risk_score=0.0, basis="not_computed_v0"),
        last_refusal=last_refusal,
    )


def _build_empty_dashboard(
    *,
    refusal: KernelRefusal | None,
    semantic_ready: bool | None,
) -> KernelDashboard:
    return KernelDashboard(
        latest_refs=KernelLatestRefs(),
        gap_summary=KernelGapSummary(),
        claimability=KernelClaimabilityStatus(claimable_ready=False, missing_claimability=[]),
        semantic_ready=semantic_ready,
        budgets_remaining={
            "steps_remaining": 0,
            "wall_time_seconds_remaining": 0,
            "retrieval_calls_remaining": 0,
            "semantic_calls_remaining": 0,
            "patch_calls_remaining": 0,
        },
        failure_classification=KernelFailureClassification(
            stop_reason=None,
            reason_code=(refusal.reason_code if refusal is not None else None),
        ),
        no_progress_risk=KernelNoProgressRisk(risk_score=0.0, basis="not_computed_v0"),
        last_refusal=refusal,
    )


def _update_latest_refs(run_artifact: RunArtifact, step: StepRecord, *, action_executor: ActionExecutor) -> None:
    """Apply registered provider/projector hooks only — no mission semantics in session."""
    projector = action_executor.deps.provider_step_projectors.get(step.action)
    if projector is not None:
        projector(run_artifact, step)


def _run_terminal_success_hooks(run_artifact: RunArtifact, *, action_executor: ActionExecutor) -> None:
    """Apply product/domain-owned terminal completion hooks only."""
    for hook in action_executor.deps.terminal_success_hooks:
        try:
            hook(run_artifact)
        except Exception:
            # Completion hooks are best-effort and must not invalidate successful terminal completion.
            continue


def _latest_validate_ref(run_artifact: RunArtifact) -> dict[str, object] | None:
    return build_latest_validate_ref(run_artifact)


def _compute_budgets_remaining(run_artifact: RunArtifact, budgets: dict[str, int]) -> dict[str, int]:
    steps_used = len(run_artifact.steps)
    retrieval_calls = sum(
        1 for step in run_artifact.steps if canonical_action_id(step.action) == ActionType.RETRIEVE_EVIDENCE.value
    )
    semantic_calls = sum(
        1
        for step in run_artifact.steps
        if canonical_action_id(step.action) == ActionType.RETRIEVE_EVIDENCE.value
        and bool(step.inputs.get("semantic", False))
    )
    patch_calls = sum(
        1 for step in run_artifact.steps if canonical_action_id(step.action) == ActionType.PROPOSE_PATCH.value
    )
    elapsed = max(0, int(time()) - int(run_artifact.created_at_epoch_seconds or int(time())))
    return {
        "steps_remaining": max(0, int(budgets.get("max_steps", 0)) - steps_used),
        "wall_time_seconds_remaining": max(0, int(budgets.get("max_wall_time_seconds", 0)) - elapsed),
        "retrieval_calls_remaining": max(0, int(budgets.get("max_retrieval_calls", 0)) - retrieval_calls),
        "semantic_calls_remaining": max(0, int(budgets.get("max_semantic_calls", 0)) - semantic_calls),
        "patch_calls_remaining": max(0, int(budgets.get("max_patch_calls", 0)) - patch_calls),
    }


def _extract_or_default_budgets(run_artifact: RunArtifact) -> dict[str, int]:
    if run_artifact.session_budgets:
        return {str(k): int(v) for k, v in run_artifact.session_budgets.items()}
    if run_artifact.idempotency_ledger:
        latest = next(reversed(run_artifact.idempotency_ledger.values()))
        if isinstance(latest, dict) and isinstance(latest.get("budgets"), dict):
            return dict(latest["budgets"])
    return {
        "max_steps": 100,
        "max_wall_time_seconds": 3600,
        "max_retrieval_calls": 100,
        "max_semantic_calls": 100,
        "max_patch_calls": 100,
    }


def _extract_budgets(entry: dict[str, object]) -> dict[str, int]:
    raw = entry.get("budgets")
    if isinstance(raw, dict):
        return {str(k): int(v) for k, v in raw.items()}
    return {
        "max_steps": 100,
        "max_wall_time_seconds": 3600,
        "max_retrieval_calls": 100,
        "max_semantic_calls": 100,
        "max_patch_calls": 100,
    }


def _coerce_terminal(raw: object) -> TerminalOutcome | None:
    if isinstance(raw, dict):
        return TerminalOutcome.model_validate(raw)
    return None


def _coerce_refusal(raw: object) -> KernelRefusal | None:
    if isinstance(raw, dict):
        return KernelRefusal.model_validate(raw)
    return None


def _lookup_step(run_artifact: RunArtifact, step_id: str) -> StepRecord | None:
    if not step_id:
        return None
    for step in run_artifact.steps:
        if step.step_id == step_id:
            return step
    return None


def _extract_tool_refusal(step: StepRecord) -> KernelRefusal | None:
    if not isinstance(step.outputs_inline, dict):
        return None
    raw_refusal = step.outputs_inline.get("kernel_refusal")
    if not isinstance(raw_refusal, dict):
        return None
    try:
        return KernelRefusal.model_validate(raw_refusal)
    except Exception:
        return None




def _tool_menu(action_executor: ActionExecutor) -> list[str]:
    """Order: harness enum order (plus declare_done), then any provider-only action ids."""
    available = list(action_executor.available_actions(allow_stubbed=False))
    avail_set = set(available)
    ordered: list[str] = []
    for action in HarnessAction:
        if action == ActionType.DECLARE_DONE:
            ordered.append(action.value)
            continue
        if action.value in avail_set:
            ordered.append(action.value)
    for aid in available:
        if aid not in ordered:
            ordered.append(aid)
    return ordered


def _persist_bootstrap_ir_graph(
    *,
    request_id: str,
    run_id: str,
    graph: dict[str, object],
) -> ArtifactRef:
    root = agent_kernel_artifacts_root() / "bootstrap_ir" / request_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{run_id}_{uuid4().hex[:8]}.json"
    payload = {
        "artifact_type": "bootstrap_ir_graph",
        "request_id": request_id,
        "run_id": run_id,
        "created_at_epoch_seconds": int(time()),
        "graph": graph,
    }
    fd, tmp_path = tempfile.mkstemp(prefix="kernel_bootstrap_", suffix=".json", dir=str(root))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        try:
            os.replace(tmp_path, str(path))
        except PermissionError:
            # Best-effort atomic behavior on Windows; fallback keeps session bootstrap reliable.
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass
    return ArtifactRef(artifact_path=str(path))
