"""CLI harness for transcript-edit agent endpoint internals."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from api.endpoints import transcript_edit_agent

_EXIT_FAILED = 1
_EXIT_NEEDS_REVIEW = 2
_EXIT_WAITING_FEEDBACK = 3


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcript-edit-agent-cli",
        description="Run kernel-backed transcript edit agent loop via backend endpoint internals.",
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--source-transcript-ref", dest="source_transcript_ref")
    source_group.add_argument("--text-file", dest="text_file")
    source_group.add_argument("--text", dest="text")
    parser.add_argument("--dossier-id", dest="dossier_id")
    parser.add_argument("--image-ref", dest="image_refs", action="append", default=[])
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--max-iterations", type=int, default=4)
    parser.add_argument(
        "--mode",
        default="audit_then_repair_then_promote",
        choices=["off", "audit_only", "audit_then_repair", "audit_then_repair_then_promote"],
    )
    parser.add_argument(
        "--validation-mode",
        default="off",
        choices=["off", "live_hitl"],
        help="Opt-in bounded validation runtime profile for faster HITL lifecycle testing.",
    )
    parser.add_argument("--no-auto-promote", action="store_true")
    parser.add_argument("--edit-plan-json", dest="edit_plan_json", help="Path to EditPlanV0 JSON.")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--json-only", action="store_true")
    return parser


def run_cli(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run_async(args))
    except KeyboardInterrupt:
        return 130


async def _run_async(args: argparse.Namespace) -> int:
    source_transcript_ref = args.source_transcript_ref
    source_text = _resolve_text(inline_text=args.text, text_file=args.text_file)
    edit_plan = _load_json_file(args.edit_plan_json) if args.edit_plan_json else None

    request = transcript_edit_agent.TranscriptEditAgentApiRequest(
        dossier_id=args.dossier_id,
        source_transcript_ref=source_transcript_ref,
        source_text=source_text,
        source_image_refs=[str(v) for v in (args.image_refs or []) if isinstance(v, str) and v.strip()],
        model=args.model,
        max_iterations=args.max_iterations,
        mode=args.mode,
        validation_mode=args.validation_mode,
        auto_promote=not bool(args.no_auto_promote),
        edit_plan=edit_plan,
        background=True,
    )
    start = await transcript_edit_agent.start_run(request)
    run_id = str(start["run_id"])
    if not args.json_only:
        _safe_print(f"[tx-agent] started run_id={run_id}")
    final = await _poll_until_terminal(
        run_id=run_id,
        poll_interval=max(0.1, float(args.poll_interval)),
        print_progress=not bool(args.json_only),
    )
    status = str(final.get("status") or "")
    if status == "waiting_feedback" and not args.json_only:
        _safe_print("[tx-agent] run paused: waiting for human feedback (resumable; not failed).")
    _print_json_safely(final)

    if status == "failed":
        return _EXIT_FAILED
    if status == "waiting_feedback":
        return _EXIT_WAITING_FEEDBACK
    snapshot = final.get("snapshot") if isinstance(final.get("snapshot"), dict) else {}
    if status == "needs_review" or str(snapshot.get("status") or "") == "needs_review":
        return _EXIT_NEEDS_REVIEW
    return 0


async def _poll_until_terminal(*, run_id: str, poll_interval: float, print_progress: bool) -> dict[str, Any]:
    last_progress_key: tuple[Any, ...] | None = None
    while True:
        snapshot = await transcript_edit_agent.get_run(run_id)
        status = str(snapshot.get("status") or "")
        if print_progress:
            progress_data = _progress_data(snapshot)
            if progress_data is not None:
                display_key, dedupe_key = progress_data
                if dedupe_key != last_progress_key:
                    _print_progress(display_key)
                    last_progress_key = dedupe_key
        if status in {"completed", "failed", "needs_review", "waiting_feedback"}:
            return snapshot
        await asyncio.sleep(poll_interval)


def _progress_data(snapshot: dict[str, Any]) -> tuple[tuple[Any, ...], tuple[Any, ...]] | None:
    body = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {}
    live = body.get("live_status") if isinstance(body.get("live_status"), dict) else {}
    if not live:
        return None
    phase = str(live.get("phase") or "").strip() or "status"
    iteration = live.get("iteration")
    event_type = str(live.get("event_type") or "").strip()
    execution_state = str(live.get("execution_state") or "").strip()
    message = str(live.get("message") or "").strip()
    elapsed_ms = live.get("elapsed_ms")
    display_key = (phase, iteration, event_type, execution_state, message, elapsed_ms)
    dedupe_key = (phase, iteration, event_type, execution_state, message)
    return display_key, dedupe_key


def _print_progress(progress_key: tuple[Any, ...]) -> None:
    phase, iteration, _event_type, _execution_state, message, elapsed_ms, *_ = progress_key
    iter_text = f"iter={iteration}" if isinstance(iteration, int) else "iter=n/a"
    elapsed_text = ""
    if isinstance(elapsed_ms, int) and elapsed_ms >= 0:
        elapsed_text = f" elapsed={elapsed_ms/1000:.1f}s"
    line = f"[tx-agent] phase={phase} {iter_text}{elapsed_text}"
    msg = str(message or "").strip()
    if msg:
        line = f"{line} :: {msg}"
    _safe_print(line)


def _print_json_safely(payload: dict[str, Any]) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    _safe_print(text)


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = str(getattr(sys.stdout, "encoding", None) or "utf-8")
        safe_text = text.encode(encoding, errors="replace").decode(encoding, errors="replace")
        print(safe_text)


def _resolve_text(*, inline_text: str | None, text_file: str | None) -> str | None:
    if isinstance(inline_text, str) and inline_text.strip():
        return inline_text.strip()
    if isinstance(text_file, str) and text_file.strip():
        return Path(text_file).read_text(encoding="utf-8").strip()
    return None


def _load_json_file(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("edit_plan_json_must_be_object")
    return payload


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
