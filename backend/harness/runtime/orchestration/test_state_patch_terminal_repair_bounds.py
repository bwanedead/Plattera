"""Boundary tests for terminal-row state-repair rails (MAPDEP-BR-023 follow-up)."""

from __future__ import annotations

import copy
import json
import math
from typing import Any, Mapping

from harness.execution.contracts import (
    ExecutionDashboard,
    ExecutionLatestRefs,
    ExecutionState,
    ExecutionStepRequest,
    ExecutionStepResult,
)
from harness.execution.session import ExecutionSessionManager
from harness.mission_state import (
    REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
    ResolutionCoveredUnit,
    ResolutionItem,
    TerminalRowConflict,
    TerminalRowConsistencyResult,
    new_mission_state,
    new_resolution_state,
)
from harness.runtime.memory import LoopMemoryState
from harness.runtime.memory.resume_snapshot import parse_kernel_resume_snapshot
from harness.runtime.orchestration.action_sequence import ActionPlanAction
from harness.runtime.orchestration.contracts import (
    ActionPlan,
    OrchestratorContext,
    SharedStateProjection,
)
from harness.runtime.orchestration.lifecycle import OrchestrationLifecycle
from harness.runtime.orchestration.orchestrator import run_orchestration_kernel_loop
from harness.runtime.orchestration.state_patch_consistency import (
    MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS,
    REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED,
    block_contradictory_closed_resolution_before_dispatch,
    canonical_terminal_conflict_identity,
    record_terminal_row_consistency_rejection,
)
from harness.runtime.orchestration.state_patch_repair_bundle import (
    MAX_FRAGMENTS,
    MAX_TOTAL_BUNDLE_CHARS,
    REASON_TERMINAL_ROW_LIVE_WORK,
    _bound_total_bundle,
    build_terminal_row_consistency_repair_bundle,
    required_clear_delta_for_fields,
)
from harness.runtime.orchestration.state_patch_repair_sanitization import (
    PRESERVE_FRAGMENT_KEYS,
    MAX_FRAGMENT_SERIALIZED_CHARS,
    sanitize_fragment,
)
from harness.runtime.orchestration.trace_collector import KernelTraceCollector

_PACK_CJ = {"pack_continuity_stub": True}


def _dashboard() -> ExecutionDashboard:
    return ExecutionDashboard(
        latest_refs=ExecutionLatestRefs(refs={}),
        budgets_remaining={},
        last_refusal=None,
    )


class RecordingSessionManager(ExecutionSessionManager):
    def __init__(self) -> None:
        super().__init__()
        self.steps: list[ExecutionStepRequest] = []

    def step(self, request: ExecutionStepRequest) -> ExecutionStepResult:  # type: ignore[override]
        self.steps.append(request)
        return ExecutionStepResult(
            session_id=request.session_id,
            idempotency_key=request.idempotency_key,
            execution_state=ExecutionState.EXECUTED,
            dashboard=_dashboard(),
        )


class _InheritSyncMixin:
    def initialize(self, context: OrchestratorContext) -> None:
        pass

    def sync(self, context: OrchestratorContext) -> SharedStateProjection:
        prior_ms = context.loop_memory.continuity.mission_state
        prior_rs = context.loop_memory.continuity.resolution_state
        return SharedStateProjection(
            mission_state=prior_ms,
            resolution_state=prior_rs,
            latest_refs=dict(context.loop_memory.continuity.latest_refs),
            active_item_id=prior_rs.active_item_id,
        )


def _seed_unit_memory() -> LoopMemoryState:
    mem = LoopMemoryState()
    rs = new_resolution_state(
        items=[
            ResolutionItem(
                item_id="item-1",
                title="Item",
                kind="claim",
                status="open",
                next_needed_step=None,
                covered_units=[
                    ResolutionCoveredUnit(
                        unit_id="unit-2",
                        title="Curve station",
                        status="open",
                        next_needed_step="verify station chain",
                    )
                ],
            )
        ],
        active_item_id="item-1",
    )
    ms = new_mission_state(
        mission_id="m1",
        loop_family="orchestration_kernel",
        objective="t",
        resolution_state=rs,
    )
    mem.continuity.mission_state = ms
    mem.continuity.resolution_state = rs
    return mem


def _omit_unit_close_plan() -> ActionPlan:
    return ActionPlan(
        actions=(
            ActionPlanAction(
                action_type="save_workspace_artifact",
                action_inputs={"draft_payload": {"x": 1}},
                alias="save",
            ),
        ),
        state_patch={
            "resolution": {
                "items": [
                    {
                        "item_id": "item-1",
                        "covered_units": [{"unit_id": "unit-2", "status": "closed"}],
                    }
                ]
            }
        },
        continuity_journal_entry=_PACK_CJ,
    )


def _fat_fragment(item_id: str) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "status": "closed",
        "summary": ("SUMMARY-" + item_id + "-") * 80,
        "verification_basis": ("BASIS-" + item_id + "-") * 80,
        "notes": ("NOTES-" + item_id + "-") * 80,
        "closure_summary": ("CLOSE-" + item_id + "-") * 40,
    }


def test_budget_omissions_count_dropped_fragments() -> None:
    conflicts = tuple(
        TerminalRowConflict(
            coordinate=f"resolution.items[item-{i}]",
            fields=("next_needed_step",),
        )
        for i in range(5)
    )
    patch = {
        "resolution": {
            "items": [_fat_fragment(f"item-{i}") for i in range(5)]
        }
    }
    result = TerminalRowConsistencyResult(
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        conflicts=conflicts,
        conflicts_omitted_count=0,
    )
    bundle = build_terminal_row_consistency_repair_bundle(state_patch=patch, result=result)
    assert bundle is not None
    assert bundle["reason"] == REASON_TERMINAL_ROW_LIVE_WORK
    retained = len(bundle["fragments"])
    assert 1 <= retained < 5
    assert bundle["conflicts_omitted_count"] == 5 - retained
    serialized = json.dumps(bundle, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    assert len(serialized) <= MAX_TOTAL_BUNDLE_CHARS
    assert "conflicts_omitted_count" in serialized


def test_nested_host_binary_and_non_json_values_are_stripped() -> None:
    payload = {
        "item_id": "item-1",
        "status": "closed",
        "absolute_path": "C:/secret/file.png",
        "workspace_root": "C:/secret",
        "path": "C:/secret/nested/real.path",
        "host_path": "C:/secret/host",
        "file_path": "C:/secret/file.png",
        "rows": [
            {
                "workspace_root": "C:/secret",
                "path": "C:/secret/row.path",
                "b64": "SECRET",
                "ok": True,
            }
        ],
        "blob": b"raw-bytes",
        "tags": {"a", "b"},
        "coords": (1, 2, 3),
        "bad_float": math.nan,
        "inf_float": math.inf,
        "nested": {"image_bytes": b"x", "label": "keep", "path": "C:/secret/deep"},
    }
    sanitized, truncated = sanitize_fragment(payload)
    assert truncated is True
    blob = json.dumps(sanitized, ensure_ascii=False, allow_nan=False)
    assert "absolute_path" not in sanitized
    assert "workspace_root" not in sanitized
    assert "path" not in sanitized
    assert "host_path" not in sanitized
    assert "file_path" not in sanitized
    assert "SECRET" not in blob
    assert "C:/secret" not in blob
    assert "blob" not in sanitized
    assert "tags" not in sanitized
    assert "coords" not in sanitized
    assert "bad_float" not in sanitized
    assert "inf_float" not in sanitized
    assert sanitized["nested"] == {"label": "keep"}
    assert sanitized["rows"] == [{"ok": True}]
    assert sanitized["item_id"] == "item-1"


def test_required_clear_delta_null_survives_sanitization() -> None:
    delta = required_clear_delta_for_fields(("next_needed_step",))
    assert delta == {"next_needed_step": None}
    re_sanitized, truncated = sanitize_fragment(delta)
    assert truncated is False
    assert re_sanitized == {"next_needed_step": None}
    assert "next_needed_step" in json.dumps(re_sanitized, allow_nan=False)


def test_preserve_fragment_keys_are_explicitly_ordered() -> None:
    assert isinstance(PRESERVE_FRAGMENT_KEYS, tuple)
    assert PRESERVE_FRAGMENT_KEYS[0] == "item_id"
    assert PRESERVE_FRAGMENT_KEYS[1] == "unit_id"
    # Pressure trim must follow the tuple order, not frozenset hash order.
    bulky = {key: ("X" * 200) for key in ("zzz_tail", *PRESERVE_FRAGMENT_KEYS, "aaa_head")}
    bulky["summary"] = "S" * 5000
    sanitized, truncated = sanitize_fragment(bulky)
    assert truncated is True
    keys = list(sanitized.keys())
    expected = [key for key in PRESERVE_FRAGMENT_KEYS if key in sanitized]
    assert keys == expected


def test_omission_marker_included_in_fit_so_final_bundle_stays_under_cap() -> None:
    """Regression: growing conflicts_omitted_count must not push the final payload over 6k."""

    def _row(n: int, *, summary_chars: int) -> dict[str, Any]:
        return {
            "path": f"resolution.items[item-{n}]",
            "reason_code": REASON_TERMINAL_ROW_LIVE_WORK,
            "conflicting_fields": ["next_needed_step"],
            "fragment": {
                "item_id": f"item-{n}",
                "status": "closed",
                "summary": "S" * summary_chars,
            },
            "required_clear_delta": {"next_needed_step": None},
        }

    def _size(payload: Mapping[str, Any]) -> int:
        return len(
            json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        )

    # Find a summary size where two fragments fit, but two + omission marker does not.
    summary_chars = 2500
    two = {
        "schema_version": 1,
        "reason": REASON_TERMINAL_ROW_LIVE_WORK,
        "instruction": "repair",
        "fragments": [_row(0, summary_chars=summary_chars), _row(1, summary_chars=summary_chars)],
    }
    while _size(two) < MAX_TOTAL_BUNDLE_CHARS - 40:
        summary_chars += 10
        two["fragments"] = [
            _row(0, summary_chars=summary_chars),
            _row(1, summary_chars=summary_chars),
        ]
    # Back off until two fit without marker.
    while _size(two) > MAX_TOTAL_BUNDLE_CHARS:
        summary_chars -= 1
        two["fragments"] = [
            _row(0, summary_chars=summary_chars),
            _row(1, summary_chars=summary_chars),
        ]
    assert _size(two) <= MAX_TOTAL_BUNDLE_CHARS

    with_marker = dict(two)
    with_marker["conflicts_omitted_count"] = 1
    # Grow until the marker alone would re-cross the cap for the two-fragment shape.
    while _size(with_marker) <= MAX_TOTAL_BUNDLE_CHARS:
        summary_chars += 1
        two["fragments"] = [
            _row(0, summary_chars=summary_chars),
            _row(1, summary_chars=summary_chars),
        ]
        with_marker = dict(two)
        with_marker["conflicts_omitted_count"] = 1
        if _size(two) > MAX_TOTAL_BUNDLE_CHARS:
            # Two alone already over — step back one and stop.
            summary_chars -= 1
            two["fragments"] = [
                _row(0, summary_chars=summary_chars),
                _row(1, summary_chars=summary_chars),
            ]
            with_marker = dict(two)
            with_marker["conflicts_omitted_count"] = 1
            break

    assert _size(two) <= MAX_TOTAL_BUNDLE_CHARS
    assert _size(with_marker) > MAX_TOTAL_BUNDLE_CHARS

    over = {
        "schema_version": 1,
        "reason": REASON_TERMINAL_ROW_LIVE_WORK,
        "instruction": "repair",
        "fragments": [
            _row(0, summary_chars=summary_chars),
            _row(1, summary_chars=summary_chars),
            _row(2, summary_chars=summary_chars),
        ],
    }
    assert _size(over) > MAX_TOTAL_BUNDLE_CHARS
    bound = _bound_total_bundle(over)
    assert _size(bound) <= MAX_TOTAL_BUNDLE_CHARS
    assert bound.get("conflicts_omitted_count", 0) >= 1
    assert (
        len(json.dumps(bound, ensure_ascii=False, allow_nan=False, separators=(",", ":")))
        <= MAX_TOTAL_BUNDLE_CHARS
    )


def test_malformed_resumed_streaks_do_not_raise() -> None:
    mem = _seed_unit_memory()
    plan = _omit_unit_close_plan()
    tracer = KernelTraceCollector(session_id="s", request_id="r")
    # Seed a valid rejection so identity is established.
    outcome = block_contradictory_closed_resolution_before_dispatch(
        loop_memory=mem,
        action_plan=plan,
        tracer=tracer,
        iteration=1,
        lifecycle=OrchestrationLifecycle(),
        session_manager=RecordingSessionManager(),
        session_id="sess-streak",
        turn_completion_observer=None,
    )
    assert outcome is not None
    identity = mem.continuity.state_patch_feedback["conflict_identity"]
    assert identity.startswith("sha256:")
    assert len(identity) == len("sha256:") + 64

    for bad in ("oops", True, False, -3, 3.5, None, {"n": 1}):
        mem.continuity.state_patch_feedback = {
            "outcome": "rejected",
            "reason_code": REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
            "conflict_identity": identity,
            "same_conflict_streak": bad,
        }
        streak = record_terminal_row_consistency_rejection(
            loop_memory=mem,
            tracer=None,
            iteration=2,
            result=TerminalRowConsistencyResult(
                reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
                conflicts=(
                    TerminalRowConflict(
                        coordinate="resolution.items[item-1].covered_units[unit-2]",
                        fields=("next_needed_step",),
                    ),
                ),
                conflicts_omitted_count=0,
            ),
            state_patch=plan.state_patch,
        )
        assert streak == 1, bad
        assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 1

    # Oversized exact ints are capped at the configured limit (no raise).
    mem.continuity.state_patch_feedback = {
        "outcome": "rejected",
        "reason_code": REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        "conflict_identity": identity,
        "same_conflict_streak": 99,
    }
    streak = record_terminal_row_consistency_rejection(
        loop_memory=mem,
        tracer=None,
        iteration=3,
        result=TerminalRowConsistencyResult(
            reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
            conflicts=(
                TerminalRowConflict(
                    coordinate="resolution.items[item-1].covered_units[unit-2]",
                    fields=("next_needed_step",),
                ),
            ),
            conflicts_omitted_count=0,
        ),
        state_patch=plan.state_patch,
    )
    assert streak == MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS
    assert (
        mem.continuity.state_patch_feedback["same_conflict_streak"]
        == MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS
    )


def test_conflict_identity_is_fixed_digest_and_sensitive_to_inputs() -> None:
    base = TerminalRowConsistencyResult(
        reason_code=REASON_RESOLUTION_TERMINAL_ROW_HAS_LIVE_WORK,
        conflicts=(
            TerminalRowConflict(
                coordinate="resolution.items[item-1]",
                fields=("next_needed_step",),
            ),
        ),
        conflicts_omitted_count=0,
    )
    identity = canonical_terminal_conflict_identity(base)
    assert identity.startswith("sha256:")
    assert len(identity) == len("sha256:") + 64

    changed_coord = TerminalRowConsistencyResult(
        reason_code=base.reason_code,
        conflicts=(
            TerminalRowConflict(
                coordinate="resolution.items[item-2]",
                fields=("next_needed_step",),
            ),
        ),
        conflicts_omitted_count=0,
    )
    changed_fields = TerminalRowConsistencyResult(
        reason_code=base.reason_code,
        conflicts=(
            TerminalRowConflict(
                coordinate="resolution.items[item-1]",
                fields=("next_needed_step", "requires_hitl"),
            ),
        ),
        conflicts_omitted_count=0,
    )
    changed_omitted = TerminalRowConsistencyResult(
        reason_code=base.reason_code,
        conflicts=base.conflicts,
        conflicts_omitted_count=2,
    )
    assert canonical_terminal_conflict_identity(changed_coord) != identity
    assert canonical_terminal_conflict_identity(changed_fields) != identity
    assert canonical_terminal_conflict_identity(changed_omitted) != identity

    # Max-shaped retained conflict set stays fixed-length.
    many = TerminalRowConsistencyResult(
        reason_code=base.reason_code,
        conflicts=tuple(
            TerminalRowConflict(
                coordinate=f"resolution.items[{'x' * 200}-{i}]",
                fields=("next_needed_step", "requires_hitl", "no_further_progress"),
            )
            for i in range(32)
        ),
        conflicts_omitted_count=9,
    )
    many_id = canonical_terminal_conflict_identity(many)
    assert len(many_id) == len(identity)


def test_checkpoint_resume_fourth_identical_conflict_still_exhausts() -> None:
    assert MAX_IDENTICAL_TERMINAL_ROW_CONFLICT_REJECTIONS == 4
    mem = _seed_unit_memory()
    plan = _omit_unit_close_plan()
    snapshots: list[dict[str, Any]] = []

    def _writer(snap: dict[str, Any]) -> None:
        snapshots.append(dict(snap))

    lifecycle = OrchestrationLifecycle(resume_checkpoint_writer=_writer)
    sm = RecordingSessionManager()
    for it in (1, 2, 3):
        outcome = block_contradictory_closed_resolution_before_dispatch(
            loop_memory=mem,
            action_plan=plan,
            tracer=KernelTraceCollector(session_id="s", request_id=f"r{it}"),
            iteration=it,
            lifecycle=lifecycle,
            session_manager=sm,
            session_id="sess-bounds",
            turn_completion_observer=None,
        )
        assert outcome is not None
        assert outcome.repair_budget_exhausted is False
    assert mem.continuity.state_patch_feedback["same_conflict_streak"] == 3
    identity = mem.continuity.state_patch_feedback["conflict_identity"]
    assert identity.startswith("sha256:")

    restored, _next_it, err = parse_kernel_resume_snapshot(copy.deepcopy(snapshots[-1]))
    assert err is None
    assert restored.continuity.state_patch_feedback["same_conflict_streak"] == 3
    assert restored.continuity.state_patch_feedback["conflict_identity"] == identity

    class _ResumeExhaust(_InheritSyncMixin):
        def evaluate_terminal(self, context, projection):
            return None

        def choose_action(self, context, projection):
            return plan

    result = run_orchestration_kernel_loop(
        orchestration_adapter=_ResumeExhaust(),
        session_manager=RecordingSessionManager(),
        session_id="sess-bounds-resume",
        run_artifact_ref=None,
        request_id_prefix="req-bounds-resume",
        opaque_run_context={},
        max_iterations=2,
        initial_loop_memory=restored,
    )
    assert result.terminal_class == "failed"
    assert result.reason_code == REASON_STATE_PATCH_CONSISTENCY_REPAIR_BUDGET_EXHAUSTED
    assert result.runtime_state["state_patch_feedback"]["same_conflict_streak"] == 4
