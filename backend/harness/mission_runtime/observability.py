from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import MissionLedger, MissionRuntimeCycleResult, MissionRuntimeRequest, ModeTransition


@dataclass(frozen=True)
class MissionTransitionObservation:
    prior_mode: str
    next_mode: str
    reason: str
    status: str
    order_anchor: int
    timestamp_epoch_seconds: int
    handed_forward_artifact_refs: tuple[str, ...] = ()
    expected_next_work: str | None = None
    resume_note_for_prior_mode: str | None = None


@dataclass(frozen=True)
class MissionCycleObservation:
    cycle_index: int
    executed_mode: str | None
    resulting_active_mode: str
    summary: str
    timestamp_epoch_seconds: int
    transition: MissionTransitionObservation | None = None


@dataclass(frozen=True)
class MissionObservation:
    mission_id: str
    objective: str | None
    request_id: str | None
    active_mode: str | None
    mode_history: tuple[str, ...]
    transition_history: tuple[MissionTransitionObservation, ...]
    high_signal_artifact_refs: tuple[str, ...]
    resumability_summary: dict[str, Any]
    mission_status: dict[str, Any]
    blocker_posture_summary: dict[str, Any]
    verification_posture_summary: dict[str, Any]
    created_at_epoch_seconds: int
    updated_at_epoch_seconds: int
    cycle_index: int
    cycles: tuple[MissionCycleObservation, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "mission_runtime": {
                "mission_id": self.mission_id,
                "objective": self.objective,
                "request_id": self.request_id,
                "active_mode": self.active_mode,
                "mode_history": list(self.mode_history),
                "transition_history": [_transition_payload(item) for item in self.transition_history],
                "high_signal_artifact_refs": list(self.high_signal_artifact_refs),
                "resumability_summary": dict(self.resumability_summary),
                "mission_status": dict(self.mission_status),
                "blocker_posture_summary": dict(self.blocker_posture_summary),
                "verification_posture_summary": dict(self.verification_posture_summary),
                "created_at_epoch_seconds": self.created_at_epoch_seconds,
                "updated_at_epoch_seconds": self.updated_at_epoch_seconds,
                "cycle_index": self.cycle_index,
                "cycles": [_cycle_payload(item) for item in self.cycles],
            }
        }


def build_mission_observation_from_runtime(
    *,
    request: MissionRuntimeRequest,
    ledger: MissionLedger,
    cycle_results: list[MissionRuntimeCycleResult],
) -> MissionObservation:
    return MissionObservation(
        mission_id=ledger.mission_id,
        objective=request.objective,
        request_id=ledger.request_id,
        active_mode=ledger.active_mode,
        mode_history=tuple(str(mode) for mode in ledger.mode_history if str(mode).strip()),
        transition_history=tuple(_transition_from_runtime(item) for item in ledger.transition_history),
        high_signal_artifact_refs=tuple(_as_str_list(ledger.high_signal_artifact_refs, dedupe=True)),
        resumability_summary={
            "resumable": ledger.resumability_summary.resumable,
            "resume_reason": ledger.resumability_summary.resume_reason,
            "resume_requirements": _as_str_list(ledger.resumability_summary.resume_requirements, dedupe=False),
        },
        mission_status={
            "terminal": ledger.mission_status.terminal,
            "terminal_class": ledger.mission_status.terminal_class,
            "reason_code": ledger.mission_status.reason_code,
        },
        blocker_posture_summary={
            "waiting_human": ledger.blocker_posture_summary.waiting_human,
            "open_blocker_count": ledger.blocker_posture_summary.open_blocker_count,
        },
        verification_posture_summary={
            "status": ledger.verification_posture_summary.status,
            "last_verification_kind": ledger.verification_posture_summary.last_verification_kind,
        },
        created_at_epoch_seconds=int(ledger.created_at_epoch_seconds),
        updated_at_epoch_seconds=int(ledger.updated_at_epoch_seconds),
        cycle_index=ledger.cycle_index,
        cycles=tuple(_cycle_from_runtime(index=idx + 1, item=result, fallback_ts=int(ledger.updated_at_epoch_seconds)) for idx, result in enumerate(cycle_results)),
    )


def parse_mission_observation_payload(payload: dict[str, Any]) -> MissionObservation:
    root = _payload_root(payload)
    transition_history = tuple(_transition_from_payload(item) for item in _as_dict_list(root.get("transition_history")))
    cycles = tuple(_cycle_from_payload(item) for item in _as_dict_list(root.get("cycles")))
    return MissionObservation(
        mission_id=_as_str(root.get("mission_id")) or "unknown_mission",
        objective=_as_str(root.get("objective")),
        request_id=_as_str(root.get("request_id")),
        active_mode=_as_str(root.get("active_mode")),
        mode_history=tuple(_as_str_list(root.get("mode_history"), dedupe=False)),
        transition_history=transition_history,
        high_signal_artifact_refs=tuple(_as_str_list(root.get("high_signal_artifact_refs"), dedupe=True)),
        resumability_summary=_as_dict(root.get("resumability_summary")),
        mission_status=_as_dict(root.get("mission_status")),
        blocker_posture_summary=_as_dict(root.get("blocker_posture_summary")),
        verification_posture_summary=_as_dict(root.get("verification_posture_summary")),
        created_at_epoch_seconds=_as_int(root.get("created_at_epoch_seconds")) or 0,
        updated_at_epoch_seconds=_as_int(root.get("updated_at_epoch_seconds")) or 0,
        cycle_index=_as_int(root.get("cycle_index")) or len(cycles),
        cycles=cycles,
    )


def _payload_root(payload: dict[str, Any]) -> dict[str, Any]:
    nested = payload.get("mission_runtime")
    if isinstance(nested, dict):
        return nested
    return payload if isinstance(payload, dict) else {}


def _transition_from_runtime(item: ModeTransition) -> MissionTransitionObservation:
    return MissionTransitionObservation(
        prior_mode=item.prior_mode,
        next_mode=item.next_mode,
        reason=item.reason,
        status=item.status,
        order_anchor=item.order_anchor,
        timestamp_epoch_seconds=int(item.timestamp_epoch_seconds),
        handed_forward_artifact_refs=tuple(_as_str_list(item.handed_forward_artifact_refs, dedupe=True)),
        expected_next_work=item.expected_next_work,
        resume_note_for_prior_mode=item.resume_note_for_prior_mode,
    )


def _transition_from_payload(item: dict[str, Any]) -> MissionTransitionObservation:
    return MissionTransitionObservation(
        prior_mode=_as_str(item.get("prior_mode")) or "unknown",
        next_mode=_as_str(item.get("next_mode")) or "unknown",
        reason=_as_str(item.get("reason")) or "unspecified_transition_reason",
        status=_as_str(item.get("status")) or "unknown",
        order_anchor=_as_int(item.get("order_anchor")) or 0,
        timestamp_epoch_seconds=_as_int(item.get("timestamp_epoch_seconds")) or 0,
        handed_forward_artifact_refs=tuple(_as_str_list(item.get("handed_forward_artifact_refs"), dedupe=True)),
        expected_next_work=_as_str(item.get("expected_next_work")),
        resume_note_for_prior_mode=_as_str(item.get("resume_note_for_prior_mode")),
    )


def _transition_payload(item: MissionTransitionObservation) -> dict[str, Any]:
    return {
        "prior_mode": item.prior_mode,
        "next_mode": item.next_mode,
        "reason": item.reason,
        "status": item.status,
        "order_anchor": item.order_anchor,
        "timestamp_epoch_seconds": item.timestamp_epoch_seconds,
        "handed_forward_artifact_refs": list(item.handed_forward_artifact_refs),
        "expected_next_work": item.expected_next_work,
        "resume_note_for_prior_mode": item.resume_note_for_prior_mode,
    }


def _cycle_from_runtime(
    *,
    index: int,
    item: MissionRuntimeCycleResult,
    fallback_ts: int,
) -> MissionCycleObservation:
    trace = item.trace_segment
    return MissionCycleObservation(
        cycle_index=index,
        executed_mode=trace.mode if trace is not None else None,
        resulting_active_mode=item.active_mode,
        summary=trace.summary if trace is not None else item.interpretation.summary,
        timestamp_epoch_seconds=int(trace.timestamp_epoch_seconds) if trace is not None else fallback_ts,
        transition=_transition_from_runtime(item.transition) if item.transition is not None else None,
    )


def _cycle_from_payload(item: dict[str, Any]) -> MissionCycleObservation:
    transition_payload = item.get("transition")
    transition = _transition_from_payload(transition_payload) if isinstance(transition_payload, dict) else None
    return MissionCycleObservation(
        cycle_index=_as_int(item.get("cycle_index")) or 0,
        executed_mode=_as_str(item.get("executed_mode")),
        resulting_active_mode=_as_str(item.get("resulting_active_mode")) or "unknown",
        summary=_as_str(item.get("summary")) or "mission_cycle",
        timestamp_epoch_seconds=_as_int(item.get("timestamp_epoch_seconds")) or 0,
        transition=transition,
    )


def _cycle_payload(item: MissionCycleObservation) -> dict[str, Any]:
    return {
        "cycle_index": item.cycle_index,
        "executed_mode": item.executed_mode,
        "resulting_active_mode": item.resulting_active_mode,
        "summary": item.summary,
        "timestamp_epoch_seconds": item.timestamp_epoch_seconds,
        "transition": _transition_payload(item.transition) if item.transition is not None else None,
    }


def _as_str(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _as_str_list(value: Any, *, dedupe: bool) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _as_str(item)
        if not text:
            continue
        if dedupe and text in out:
            continue
        out.append(text)
    return out
