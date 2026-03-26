from __future__ import annotations

import json
from pathlib import Path
import sys

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
    ModeTransitionRecommendation,
    TerminalRecommendation,
)
from harness.mission_runtime.registry import MissionModeAdapterRegistry


class _DeedTerminalAdapter(MissionModeAdapter):
    mode_name = "deed_to_ir"

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
            summary="deed_done",
            family_coordination=MappingFamilyCoordination(
                current_mode="deed_to_ir",
                posture="no_handoff",
                coordination_state="no_handoff",
                summary="mapping family sees deed_to_ir posture no_handoff; no transition recommended",
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
        return ModeInterpretation(summary="deed_done")

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


class _DeedTransitionAdapter(_DeedTerminalAdapter):
    def recommend(
        self,
        *,
        request: MissionRuntimeRequest,
        ledger: MissionLedgerView,
        context: ModeCycleContext,
        interpretation: ModeInterpretation,
    ) -> ModeRecommendation:
        del request, context, interpretation
        if ledger.cycle_index == 0:
            return ModeRecommendation(
                transition=ModeTransitionRecommendation(
                    next_mode="transcript_edit",
                    reason="handoff_to_transcript",
                    handed_forward_artifact_refs=["artifact://handoff/deed"],
                    expected_next_work="review transcript",
                    resume_note_for_prior_mode="resume deed after transcript checks",
                ),
                terminal=TerminalRecommendation(terminal=True, terminal_class="completed", reason_code="deed_ready"),
            )
        return ModeRecommendation(
            terminal=TerminalRecommendation(terminal=True, terminal_class="completed", reason_code="deed_done"),
        )


class _TranscriptTransitionAdapter(MissionModeAdapter):
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
                posture="ready_for_downstream_domain",
                target_domain_id="deed_to_ir",
                target_family_id="mapping",
                coordination_state="transition_recommended",
                summary="mapping family recommends transition from transcript_edit to deed_to_ir for ready_for_downstream_domain posture",
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
            transition=ModeTransitionRecommendation(
                next_mode="deed_to_ir",
                reason="handoff_back_to_deed",
                handed_forward_artifact_refs=["artifact://handoff/transcript"],
                expected_next_work="resume deed synthesis",
                resume_note_for_prior_mode="return only if blockers reopen",
            ),
            terminal=TerminalRecommendation(terminal=True, terminal_class="completed", reason_code="tx_ready"),
        )


def test_mission_runtime_cli_emits_canonical_payload(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        mission_runtime_cli,
        "_build_adapter_registry",
        lambda args, mission_request: MissionModeAdapterRegistry([_DeedTerminalAdapter()]),
    )
    code = mission_runtime_cli.run_cli(
        [
            "--objective",
            "cli smoke test",
            "--initial-mode",
            "deed_to_ir",
            "--deed-text",
            "Example deed body",
            "--json-only",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["cli_surface"] == "mission_runtime_cli"
    assert payload["canonical_surface"] is True
    assert set(payload.keys()) == {"cli_surface", "canonical_surface", "mission_runtime"}
    mission_runtime = payload["mission_runtime"]
    assert mission_runtime["active_mode"] == "deed_to_ir"
    assert mission_runtime["mode_history"] == ["deed_to_ir"]
    assert mission_runtime["family_coordination"]["family_id"] == "mapping"
    assert mission_runtime["family_coordination"]["current_mode"] == "deed_to_ir"


def test_mission_runtime_cli_supports_linear_roundtrip_shape(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        mission_runtime_cli,
        "_build_adapter_registry",
        lambda args, mission_request: MissionModeAdapterRegistry([_DeedTransitionAdapter(), _TranscriptTransitionAdapter()]),
    )
    code = mission_runtime_cli.run_cli(
        [
            "--objective",
            "roundtrip test",
            "--initial-mode",
            "deed_to_ir",
            "--deed-text",
            "Example deed body",
            "--enable-roundtrip",
            "--max-cycles",
            "3",
            "--json-only",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    mission_runtime = payload["mission_runtime"]
    assert mission_runtime["mode_history"] == ["deed_to_ir", "transcript_edit", "deed_to_ir"]
    assert len(mission_runtime["transition_history"]) == 2
    assert mission_runtime["family_coordination"]["family_id"] == "mapping"
    assert mission_runtime["family_coordination"]["current_mode"] == "deed_to_ir"
    assert mission_runtime["family_coordination"]["posture"] == "no_handoff"
    assert mission_runtime["cycles"][0]["executed_mode"] == "deed_to_ir"
    assert mission_runtime["cycles"][0]["resulting_active_mode"] == "transcript_edit"
    assert mission_runtime["cycles"][1]["executed_mode"] == "transcript_edit"
    assert mission_runtime["cycles"][1]["resulting_active_mode"] == "deed_to_ir"
