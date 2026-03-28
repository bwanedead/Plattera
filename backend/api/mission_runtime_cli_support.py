from __future__ import annotations

from agents.deed_to_ir.mission_mode_adapter import DEED_TO_IR_MODE_NAME
from agents.deed_to_ir.mission_runtime_cli_bridge import (
    DeedModeCliInputs,
    build_deed_mode_adapter_from_cli_inputs,
)
from agents.transcript_edit.mission_mode_adapter import TRANSCRIPT_EDIT_MODE_NAME
from agents.transcript_edit.mission_runtime_cli_bridge import (
    TranscriptModeCliInputs,
    build_transcript_mode_adapter_from_cli_inputs,
    resolve_tx_scenario,
)
from harness.mission_runtime.contracts import MissionModeAdapter, MissionRuntimeRequest


def build_policy_list_for_cli(
    *,
    mission_request: MissionRuntimeRequest,
    deed_inputs: DeedModeCliInputs | None,
    transcript_inputs: TranscriptModeCliInputs | None,
) -> list[MissionModeAdapter]:
    policies: list[MissionModeAdapter] = []
    needs_deed = (
        mission_request.initial_mode == DEED_TO_IR_MODE_NAME
        or bool(mission_request.metadata.get("transcript_edit_transition_to_deed_to_ir"))
    )
    needs_tx = (
        mission_request.initial_mode == TRANSCRIPT_EDIT_MODE_NAME
        or bool(mission_request.metadata.get("deed_to_ir_transition_to_transcript_edit"))
    )
    if needs_deed:
        if deed_inputs is None:
            raise ValueError("deed_mode_inputs_required")
        policies.append(build_deed_mode_adapter_from_cli_inputs(deed_inputs, mission_request=mission_request))
    if needs_tx:
        if transcript_inputs is None:
            raise ValueError("transcript_mode_inputs_required")
        policies.append(
            build_transcript_mode_adapter_from_cli_inputs(
                inputs=transcript_inputs,
                mission_request=mission_request,
            )
        )
    return policies


__all__ = [
    "DEED_TO_IR_MODE_NAME",
    "TRANSCRIPT_EDIT_MODE_NAME",
    "DeedModeCliInputs",
    "TranscriptModeCliInputs",
    "build_policy_list_for_cli",
    "resolve_tx_scenario",
]
