"""CLI harness for transcription-edit loop endpoint internals.

Legacy compatibility CLI for deterministic transcription-edit v0 endpoint
internals. Canonical harness-facing transcript-edit CLI is
``api.transcript_edit_agent_cli``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from api.endpoints import transcription_edit
from transcription_edit_loop.contracts import (
    EditLoopStartRequestV0,
    EditPlanV0,
    TranscriptionEditRunRequestV0,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="transcription-edit-cli",
        description=(
            "Run deterministic transcription-edit v0 endpoint internals "
            "(legacy compatibility surface; unified mission CLI is mission-runtime-cli)."
        ),
    )
    parser.add_argument("--dossier-id", dest="dossier_id")
    parser.add_argument("--transcript-ref", dest="transcript_ref")
    parser.add_argument("--text-file", dest="text_file")
    parser.add_argument("--text", dest="text")
    parser.add_argument("--plan-json", dest="plan_json", help="Path to EditPlanV0 JSON.")
    parser.add_argument(
        "--mode",
        choices=["audit_only", "repair", "repair_then_promote"],
        default="repair",
    )
    parser.add_argument("--promote-for-mapping", action="store_true")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--json-only", action="store_true")
    return parser


def run_cli(argv: Sequence[str] | None = None, stdout: TextIO | None = None, stderr: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    out = stdout or sys.stdout
    err = stderr or sys.stderr
    try:
        return asyncio.run(_run_cli_async(args, out=out, err=err))
    except KeyboardInterrupt:
        err.write("Interrupted\n")
        return 130


async def _run_cli_async(args: argparse.Namespace, *, out: TextIO, err: TextIO) -> int:
    source_text = _resolve_text(args.text, args.text_file)
    source_ref = (args.transcript_ref or "").strip() or None
    if bool(source_text) == bool(source_ref):
        raise SystemExit("Provide exactly one source: --transcript-ref or (--text/--text-file).")

    plan = None
    if args.plan_json:
        payload = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
        plan = EditPlanV0.model_validate(payload)

    request = transcription_edit.StartTranscriptionEditRequest(
        start=EditLoopStartRequestV0(
            dossier_id=args.dossier_id,
            source_transcript_ref=source_ref,
            source_text=source_text,
            mode=args.mode,
        ),
        plan=plan,
        promote_for_mapping=bool(args.promote_for_mapping),
        background=True,
    )
    started = await transcription_edit.start_run(request)
    run_id = str(started.get("run_id"))
    if not bool(args.json_only):
        out.write(f"[transcription-edit] started run_id={run_id} status={started.get('status')}\n")
        out.flush()

    snapshot = await _poll_until_terminal(
        run_id=run_id,
        poll_interval=max(0.1, float(args.poll_interval)),
        out=out,
        json_only=bool(args.json_only),
    )
    out.write(json.dumps(snapshot, ensure_ascii=False, indent=2))
    out.write("\n")
    out.flush()
    status = str(snapshot.get("status") or "")
    if status == "failed":
        return 1
    return 0


def _resolve_text(inline_text: str | None, text_file: str | None) -> str | None:
    if inline_text and inline_text.strip():
        return inline_text.strip()
    if text_file and text_file.strip():
        return Path(text_file).read_text(encoding="utf-8").strip()
    return None


async def _poll_until_terminal(
    *,
    run_id: str,
    poll_interval: float,
    out: TextIO,
    json_only: bool,
) -> dict[str, Any]:
    last_status: str | None = None
    while True:
        snapshot = await transcription_edit.get_run(run_id)
        status = str(snapshot.get("status") or "unknown")
        if not json_only and status != last_status:
            out.write(f"[transcription-edit] run_id={run_id} status={status}\n")
            out.flush()
            last_status = status
        if status in {"completed", "failed"}:
            return snapshot
        await asyncio.sleep(poll_interval)


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
