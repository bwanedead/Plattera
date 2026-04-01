"""Public entrypoints and registration for ``SharedRunSummaryEnvelope`` builders."""

from __future__ import annotations

from typing import Any

from .registry import register_run_summary_builder, require_run_summary_builder
from .payload import build_mission_flow_run_summary
from .models import SharedRunSummaryEnvelope
from .orchestration import build_orchestration_kernel_run_summary


def build_registered_run_summary(*, loop_family: str, payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    builder = require_run_summary_builder(loop_family)
    return builder(payload)


def _build_mission_flow_run_summary_from_payload(payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    mission_flow_payload: dict[str, Any] | None = None
    nested = payload.get("mission_flow")
    if isinstance(nested, dict):
        mission_flow_payload = nested
    if mission_flow_payload is None:
        mission_flow_payload = payload if isinstance(payload, dict) else {}
    if not isinstance(mission_flow_payload, dict):
        raise ValueError("invalid mission_flow payload for run_summary")
    return build_mission_flow_run_summary(mission_flow_payload=mission_flow_payload)


def _build_orchestration_kernel_run_summary_from_payload(payload: dict[str, Any]) -> SharedRunSummaryEnvelope:
    orchestration_kernel_payload = payload.get("orchestration_kernel")
    if not isinstance(orchestration_kernel_payload, dict):
        orchestration_kernel_payload = payload if isinstance(payload, dict) else {}
    if not isinstance(orchestration_kernel_payload, dict):
        raise ValueError("invalid orchestration_kernel payload for run_summary")
    return build_orchestration_kernel_run_summary(orchestration_kernel_payload=orchestration_kernel_payload)


register_run_summary_builder(
    loop_family="orchestration_kernel",
    builder=_build_orchestration_kernel_run_summary_from_payload,
)
register_run_summary_builder(
    loop_family="mission_flow",
    builder=_build_mission_flow_run_summary_from_payload,
)

__all__ = [
    "build_mission_flow_run_summary",
    "build_orchestration_kernel_run_summary",
    "build_registered_run_summary",
]
