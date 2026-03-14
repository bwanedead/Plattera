"""Canonical CLI for unified mission-runtime dev/testing flows.

This CLI is the preferred entry surface for exercising mission-runtime modes:
- deed_to_ir
- transcript_edit
- linear cross-mode transitions (when enabled)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import time
from typing import Any, Sequence, TextIO
from uuid import uuid4

from harness.mission_runtime.contracts import MissionRuntimeRequest
from harness.mission_runtime.modes import DEED_TO_IR_MODE_NAME, TRANSCRIPT_EDIT_MODE_NAME
from harness.mission_runtime.cli_support import (
    DeedModeCliInputs,
    TranscriptModeCliInputs,
    build_mission_cli_payload,
    build_policy_list_for_cli,
)
from harness.mission_runtime.registry import ModePolicyRegistry
from harness.mission_runtime.runtime import MissionRuntime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mission-runtime-cli",
        description=(
            "Canonical unified mission-runtime CLI for development/testing. "
            "Legacy family CLIs remain available as compatibility/debug surfaces."
        ),
    )
    parser.add_argument("--objective", required=True, help="Mission objective text.")
    parser.add_argument(
        "--initial-mode",
        default=DEED_TO_IR_MODE_NAME,
        choices=[DEED_TO_IR_MODE_NAME, TRANSCRIPT_EDIT_MODE_NAME],
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
    parser.add_argument(
        "--enable-roundtrip",
        action="store_true",
        help="Enable linear transitions: deed_to_ir -> transcript_edit -> deed_to_ir.",
    )
    parser.add_argument(
        "--enable-deed-to-transcript",
        action="store_true",
        help="Enable deed_to_ir transition recommendation path.",
    )
    parser.add_argument(
        "--enable-transcript-to-deed",
        action="store_true",
        help="Enable transcript_edit transition recommendation path.",
    )

    deed_source = parser.add_mutually_exclusive_group(required=False)
    deed_source.add_argument("--deed-dossier-id", dest="deed_dossier_id", help="Existing dossier id for deed_to_ir.")
    deed_source.add_argument("--deed-text-file", dest="deed_text_file", help="Path to deed text file.")
    deed_source.add_argument("--deed-text", dest="deed_text", help="Inline deed text.")
    parser.add_argument("--deed-initial-ir-ref", dest="deed_initial_ir_ref", help="Existing IR artifact ref.")
    parser.add_argument("--deed-model", default="gpt-5.2")
    parser.add_argument("--deed-max-iterations", type=int, default=20)
    deed_gp = parser.add_mutually_exclusive_group(required=False)
    deed_gp.add_argument("--deed-global-placement", action="store_true", dest="deed_requires_global_placement")
    deed_gp.add_argument(
        "--deed-no-global-placement",
        action="store_false",
        dest="deed_requires_global_placement",
    )
    deed_rr = parser.add_mutually_exclusive_group(required=False)
    deed_rr.add_argument("--deed-render-required", action="store_true", dest="deed_render_required")
    deed_rr.add_argument("--deed-no-render-required", action="store_false", dest="deed_render_required")
    parser.set_defaults(
        deed_requires_global_placement=True,
        deed_render_required=True,
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
    parser.add_argument(
        "--tx-use-orchestration-kernel",
        action="store_true",
        dest="tx_use_orchestration_kernel",
        help="Route transcript-edit through the orchestration kernel instead of the legacy controller loop.",
    )
    parser.add_argument(
        "--deed-use-orchestration-kernel",
        action="store_true",
        dest="deed_use_orchestration_kernel",
        help="Route deed-to-IR through the orchestration kernel instead of the legacy controller loop.",
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
        registry = _build_policy_registry(args=args, mission_request=mission_request)
        runtime = MissionRuntime(policy_registry=registry)
        cycle_results: list[Any] = []
        ledger = None
        for _ in range(max(1, int(args.max_cycles))):
            cycle = runtime.run_cycle(request=mission_request, ledger=ledger)
            cycle_results.append(cycle)
            ledger = cycle.ledger
            if cycle.ledger.mission_status.terminal and cycle.transition is None:
                break

        assert ledger is not None
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
    deed_text = _resolve_text(args.deed_text, args.deed_text_file)
    tx_text = _resolve_text(args.tx_text, args.tx_text_file)
    has_deed_source = bool(args.deed_dossier_id or deed_text or args.deed_initial_ir_ref)
    has_tx_source = bool(args.tx_source_transcript_ref or tx_text)

    if args.initial_mode == DEED_TO_IR_MODE_NAME and not has_deed_source:
        parser.error(
            "deed_to_ir requires one of --deed-dossier-id, --deed-text-file, --deed-text, or --deed-initial-ir-ref."
        )
    if args.initial_mode == TRANSCRIPT_EDIT_MODE_NAME and not has_tx_source:
        parser.error("transcript_edit requires one of --tx-source-transcript-ref, --tx-text-file, or --tx-text.")

    if int(args.max_cycles) < 1:
        parser.error("--max-cycles must be >= 1")


def _build_mission_runtime_request(args: argparse.Namespace) -> MissionRuntimeRequest:
    mission_id = str(args.mission_id or f"mission_{int(time())}_{uuid4().hex[:8]}")
    metadata: dict[str, Any] = {}
    deed_to_tx = bool(args.enable_roundtrip or args.enable_deed_to_transcript)
    tx_to_deed = bool(args.enable_roundtrip or args.enable_transcript_to_deed)
    if deed_to_tx or tx_to_deed:
        metadata["phase_e_enable_linear_transitions"] = True
    if deed_to_tx:
        metadata["deed_to_ir_transition_to_transcript_edit"] = True
    if tx_to_deed:
        metadata["transcript_edit_transition_to_deed_to_ir"] = True
    return MissionRuntimeRequest(
        mission_id=mission_id,
        objective=str(args.objective),
        initial_mode=str(args.initial_mode),
        request_id=(str(args.request_id).strip() if isinstance(args.request_id, str) and args.request_id.strip() else None),
        metadata=metadata,
    )


def _build_policy_registry(
    *,
    args: argparse.Namespace,
    mission_request: MissionRuntimeRequest,
) -> ModePolicyRegistry:
    deed_inputs = DeedModeCliInputs(
        dossier_id=args.deed_dossier_id,
        deed_text=_resolve_text(args.deed_text, args.deed_text_file),
        initial_ir_ref=args.deed_initial_ir_ref,
        model=str(args.deed_model),
        max_iterations=max(1, int(args.deed_max_iterations)),
        requires_global_placement=bool(args.deed_requires_global_placement),
        render_required=bool(args.deed_render_required),
        use_orchestration_kernel=bool(args.deed_use_orchestration_kernel),
    )
    transcript_inputs = TranscriptModeCliInputs(
        dossier_id=args.tx_dossier_id,
        source_transcript_ref=args.tx_source_transcript_ref,
        source_text=_resolve_text(args.tx_text, args.tx_text_file),
        model=str(args.tx_model),
        max_iterations=max(1, int(args.tx_max_iterations)),
        mode=str(args.tx_mode),
        validation_mode=str(args.tx_validation_mode),
        auto_promote=not bool(args.tx_no_auto_promote),
        use_orchestration_kernel=bool(args.tx_use_orchestration_kernel),
    )
    policies = build_policy_list_for_cli(
        mission_request=mission_request,
        deed_inputs=deed_inputs,
        transcript_inputs=transcript_inputs,
    )
    return ModePolicyRegistry(policies)


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
