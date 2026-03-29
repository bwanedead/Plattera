from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api import mission_runtime_cli
from harness.mission_runtime.contracts import (
    MappingFamilyCoordination,
    MissionLedgerView,
    MissionModeAdapter,
    MissionRuntimeRequest,
    MissionModeRunEnvelope,
    ModeCycleContext,
    ModeInterpretation,
    ModeRecommendation,
    TerminalRecommendation,
)
from harness.mission_runtime.registry import MissionModeAdapterRegistry


class _TranscriptTerminalAdapter(MissionModeAdapter):
    mode_name = "transcript_edit"

    def build_context(self, *, request: MissionRuntimeRequest, ledger: MissionLedgerView) -> ModeCycleContext:
        del request, ledger
        return ModeCycleContext(payload={})

    def build_run_envelope(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> MissionModeRunEnvelope:
        del request, ledger, context
        return MissionModeRunEnvelope(
            summary="transcript_done",
            family_coordination=MappingFamilyCoordination(
                current_mode="transcript_edit",
                posture="no_handoff",
                coordination_state="no_handoff",
                summary="mapping family sees transcript_edit posture no_handoff; no transition recommended",
            ),
        )

    def interpret(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
    ) -> ModeInterpretation:
        del request, ledger, context
        return ModeInterpretation(summary="transcript_done")

    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        del request, ledger, context, interpretation
        return ModeRecommendation(
            terminal=TerminalRecommendation(terminal=True, terminal_class="completed", reason_code="ok"),
        )


def test_mission_runtime_cli_emits_canonical_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        mission_runtime_cli,
        "_build_adapter_registry",
        lambda args, mission_request: MissionModeAdapterRegistry([_TranscriptTerminalAdapter()]),
    )
    code = mission_runtime_cli.run_cli(
        [
            "--objective",
            "cli smoke test",
            "--initial-mode",
            "transcript_edit",
            "--tx-text",
            "Example transcript body",
            "--json-only",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cli_surface"] == "mission_runtime_cli"
    assert payload["canonical_surface"] is True
    assert set(payload.keys()) == {"cli_surface", "canonical_surface", "mission_runtime"}
    mission_runtime = payload["mission_runtime"]
    assert mission_runtime["active_mode"] == "transcript_edit"
    assert mission_runtime["mode_history"] == ["transcript_edit"]
    assert mission_runtime["family_coordination"]["family_id"] == "mapping"
    assert mission_runtime["family_coordination"]["current_mode"] == "transcript_edit"


def test_mission_runtime_cli_rejects_retired_deed_mode_choice() -> None:
    with pytest.raises(SystemExit):
        mission_runtime_cli.run_cli(
            [
                "--objective",
                "retired deed mode test",
                "--initial-mode",
                "deed_to_ir",
                "--tx-text",
                "Example transcript body",
                "--json-only",
            ]
        )
