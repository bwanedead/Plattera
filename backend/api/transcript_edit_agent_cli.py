"""CLI harness for transcript-edit agent endpoint internals."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from api.endpoints import transcript_edit_agent


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
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--max-iterations", type=int, default=4)
    parser.add_argument(
        "--mode",
        default="audit_then_repair_then_promote",
        choices=["off", "audit_only", "audit_then_repair", "audit_then_repair_then_promote"],
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
        model=args.model,
        max_iterations=args.max_iterations,
        mode=args.mode,
        auto_promote=not bool(args.no_auto_promote),
        edit_plan=edit_plan,
        background=True,
    )
    start = await transcript_edit_agent.start_run(request)
    run_id = str(start["run_id"])
    if not args.json_only:
        print(f"[tx-agent] started run_id={run_id}")
    final = await _poll_until_terminal(run_id=run_id, poll_interval=max(0.1, float(args.poll_interval)))
    print(json.dumps(final, ensure_ascii=False, indent=2))

    status = str(final.get("status") or "")
    if status == "failed":
        return 1
    snapshot = final.get("snapshot") if isinstance(final.get("snapshot"), dict) else {}
    if status == "needs_review" or str(snapshot.get("status") or "") == "needs_review":
        return 2
    return 0


async def _poll_until_terminal(*, run_id: str, poll_interval: float) -> dict[str, Any]:
    while True:
        snapshot = await transcript_edit_agent.get_run(run_id)
        status = str(snapshot.get("status") or "")
        if status in {"completed", "failed", "needs_review"}:
            return snapshot
        await asyncio.sleep(poll_interval)


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
