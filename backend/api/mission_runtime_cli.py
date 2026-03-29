"""Canonical CLI for unified mission-runtime dev/testing flows.

This CLI is the preferred entry surface for exercising mission-runtime modes:
- transcript_edit
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import time
from typing import Any, Sequence, TextIO
from uuid import uuid4

from domains.mapping.transcript_edit.mission_mode_adapter import TRANSCRIPT_EDIT_MODE_NAME
from services.workflows.mapping.transcription_edit.mission_runtime_cli_bridge import (
    TranscriptModeCliInputs,
    build_transcript_mode_adapter_from_cli_inputs,
    resolve_tx_scenario,
)
from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.cli_support import (
    build_mission_cli_payload,
    persist_mission_trace_index,
)
from harness.mission_runtime.registry import MissionModeAdapterRegistry
from harness.mission_runtime.runtime import MissionRuntime
from harness.mission_runtime.contracts import MissionModeAdapter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mission-runtime-cli",
        description=(
            "Canonical unified mission-runtime CLI for development/testing. "
            "Transcript-edit mode is the active supported runtime surface in this convergence phase."
        ),
    )
    parser.add_argument("--objective", required=True, help="Mission objective text.")
    parser.add_argument(
        "--initial-mode",
        default=TRANSCRIPT_EDIT_MODE_NAME,
        choices=[TRANSCRIPT_EDIT_MODE_NAME],
        help="Initial mission mode.",
    )
    parser.add_argument("--mission-id", dest="mission_id", help="Optional mission id; auto-generated when omitted.")
    parser.add_argument("--request-id", dest="request_id", help="Optional request id.")
    parser.add_argument("--max-cycles", type=int, default=1, help="Maximum mission cycles to execute.")
    parser.add_argument("--json-only", action="store_true", help="Print only final JSON payload.")
    parser.add_argument(
        "--done-file",
        dest="done_file",
        default=None,
        help=(
            "Path to write a done-sentinel JSON file when the run completes. "
            "Used by hitl_watch for agent-mode testing so it knows when the loop finishes."
        ),
    )
    tx_source = parser.add_mutually_exclusive_group(required=False)
    tx_source.add_argument("--tx-source-transcript-ref", dest="tx_source_transcript_ref")
    tx_source.add_argument("--tx-text-file", dest="tx_text_file")
    tx_source.add_argument("--tx-text", dest="tx_text")
    parser.add_argument("--tx-dossier-id", dest="tx_dossier_id")
    parser.add_argument("--tx-model", default="gpt-5.2")
    parser.add_argument("--tx-max-iterations", type=int, default=4)
    parser.add_argument(
        "--tx-mode",
        default="audit_then_repair_then_promote",
        choices=["off", "audit_only", "audit_then_repair", "audit_then_repair_then_promote"],
    )
    parser.add_argument(
        "--tx-validation-mode",
        default="off",
        choices=["off", "live_hitl"],
    )
    parser.add_argument("--tx-no-auto-promote", action="store_true")
    # Named test scenarios (D3).
    parser.add_argument(
        "--tx-scenario",
        dest="tx_scenario",
        default=None,
        choices=["practice_legaltext"],
        help=(
            "Named practice scenario. Resolves --tx-dossier-id and --tx-source-transcript-ref "
            "automatically. 'practice_legaltext' uses the legal-text image dossier with the "
            "known range 74/75 conflict (see docs/transcript-edit-live-validation-path-2026-03-08.md)."
        ),
    )
    return parser


def run_cli(argv: Sequence[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    try:
        _validate_args(args, parser=parser)
        mission_request = _build_mission_runtime_request(args)
        registry = _build_adapter_registry(args=args, mission_request=mission_request)
        runtime = MissionRuntime(adapter_registry=registry)
        cycle_results: list[Any] = []
        ledger = None
        for _ in range(max(1, int(args.max_cycles))):
            cycle = runtime.run_cycle(request=mission_request, ledger=ledger)
            cycle_results.append(cycle)
            ledger = cycle.ledger
            if cycle.ledger.mission_status.terminal and cycle.transition is None:
                break

        assert ledger is not None

        _mission_trace_ref = persist_mission_trace_index(
            mission_request=mission_request,
            ledger=ledger,
            cycle_results=cycle_results,
        )
        if _mission_trace_ref:
            ledger.high_signal_artifact_refs = [
                r for r in ledger.high_signal_artifact_refs if r != _mission_trace_ref
            ] + [_mission_trace_ref]

        payload = build_mission_cli_payload(
            mission_request=mission_request,
            ledger=ledger,
            cycle_results=cycle_results,
        )
        out.write(json.dumps(payload, ensure_ascii=False, indent=2))
        out.write("\n")
        out.flush()
        mission_runtime = payload.get("mission_runtime") if isinstance(payload, dict) else {}
        mission_status = mission_runtime.get("mission_status") if isinstance(mission_runtime, dict) else {}
        _write_done_sentinel(args=args, mission_status=mission_status)
        if isinstance(mission_status, dict) and not bool(mission_status.get("terminal", False)):
            return 2
        return 0
    except SystemExit:
        raise
    except Exception as exc:
        _write_done_sentinel(args=args, mission_status={"terminal": True, "error": str(exc)})
        err.write(f"mission-runtime-cli failed: {type(exc).__name__}: {exc}\n")
        err.flush()
        return 1


def _validate_args(args: argparse.Namespace, *, parser: argparse.ArgumentParser) -> None:
    tx_text = _resolve_text(args.tx_text, args.tx_text_file)
    has_tx_source = bool(args.tx_source_transcript_ref or tx_text)

    if not has_tx_source and not args.tx_scenario:
        parser.error(
            "transcript_edit requires one of --tx-source-transcript-ref, --tx-text-file, --tx-text, "
            "or --tx-scenario <name>."
        )

    if int(args.max_cycles) < 1:
        parser.error("--max-cycles must be >= 1")


def _build_mission_runtime_request(args: argparse.Namespace) -> MissionRuntimeRequest:
    mission_id = str(args.mission_id or f"mission_{int(time())}_{uuid4().hex[:8]}")
    return MissionRuntimeRequest(
        mission_id=mission_id,
        objective=str(args.objective),
        initial_mode=str(args.initial_mode),
        request_id=(str(args.request_id).strip() if isinstance(args.request_id, str) and args.request_id.strip() else None),
        metadata={},
    )


def _build_adapter_registry(
    *,
    args: argparse.Namespace,
    mission_request: MissionRuntimeRequest,
) -> MissionModeAdapterRegistry:
    # Resolve named scenario first — it may supply dossier_id and transcript_ref.
    tx_dossier_id = args.tx_dossier_id
    tx_source_ref = args.tx_source_transcript_ref
    if args.tx_scenario:
        scenario_dossier, scenario_ref = resolve_tx_scenario(args.tx_scenario)
        if scenario_dossier and not tx_dossier_id:
            tx_dossier_id = scenario_dossier
        if scenario_ref and not tx_source_ref:
            tx_source_ref = scenario_ref
        elif not scenario_ref and not tx_source_ref:
            raise SystemExit(
                f"Scenario '{args.tx_scenario}': transcript seed not found in local dossiers store.\n"
                "Ensure the practice dossier has been imported, or supply "
                "--tx-source-transcript-ref explicitly."
            )

    transcript_inputs = TranscriptModeCliInputs(
        dossier_id=tx_dossier_id,
        source_transcript_ref=tx_source_ref,
        source_text=_resolve_text(args.tx_text, args.tx_text_file),
        model=str(args.tx_model),
        max_iterations=max(1, int(args.tx_max_iterations)),
        mode=str(args.tx_mode),
        validation_mode=str(args.tx_validation_mode),
        auto_promote=not bool(args.tx_no_auto_promote),
    )
    policies = build_policy_list_for_cli(
        mission_request=mission_request,
        transcript_inputs=transcript_inputs,
    )
    return MissionModeAdapterRegistry(policies)


def build_policy_list_for_cli(
    *,
    mission_request: MissionRuntimeRequest,
    transcript_inputs: TranscriptModeCliInputs | None,
) -> list[MissionModeAdapter]:
    policies: list[MissionModeAdapter] = []
    if mission_request.initial_mode != TRANSCRIPT_EDIT_MODE_NAME:
        raise ValueError("transcript_edit_mode_required")
    if transcript_inputs is None:
        raise ValueError("transcript_mode_inputs_required")
    policies.append(
        build_transcript_mode_adapter_from_cli_inputs(
            inputs=transcript_inputs,
            mission_request=mission_request,
        )
    )
    return policies


def _resolve_text(inline_text: str | None, text_file: str | None) -> str | None:
    if isinstance(inline_text, str) and inline_text.strip():
        return inline_text.strip()
    if isinstance(text_file, str) and text_file.strip():
        return Path(text_file).read_text(encoding="utf-8").strip()
    return None


def _write_done_sentinel(*, args: Any, mission_status: Any) -> None:
    """Write a done-sentinel file so hitl_watch knows the loop has finished."""
    done_file = getattr(args, "done_file", None)
    if not done_file:
        return
    try:
        sentinel = {
            "terminal": bool((mission_status or {}).get("terminal", True)),
            "status": (mission_status or {}).get("terminal_class") or (mission_status or {}).get("status"),
            "reason_code": (mission_status or {}).get("reason_code"),
        }
        Path(done_file).parent.mkdir(parents=True, exist_ok=True)
        Path(done_file).write_text(json.dumps(sentinel, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()


