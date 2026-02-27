"""CLI harness for running the backend agent-loop endpoint path without the UI."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Sequence, TextIO

from api.endpoints import agent_loop
from config.paths import dossiers_state_root


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-loop-cli",
        description="Run the controller-driven text-to-schema agent loop via backend endpoint internals.",
    )
    bootstrap = parser.add_mutually_exclusive_group(required=False)
    bootstrap.add_argument("--dossier-id", dest="dossier_id", help="Use an existing dossier as the loop input.")
    bootstrap.add_argument(
        "--finalized-title",
        dest="finalized_title",
        help="Select a finalized dossier from the canonical finalized index by title substring (case-insensitive).",
    )
    bootstrap.add_argument(
        "--right-of-way",
        action="store_true",
        help="Use the canonical finalized 'Right of Way Deed' dossier from finalized_index.json.",
    )
    bootstrap.add_argument("--text-file", dest="text_file", help="Path to deed/finalized text file to bootstrap a run.")
    bootstrap.add_argument("--text", dest="text", help="Inline deed/finalized text to bootstrap a run.")
    parser.add_argument("--initial-ir-ref", dest="initial_ir_ref", help="Start from an existing IR artifact ref.")
    parser.add_argument(
        "--list-finalized",
        action="store_true",
        help="List canonical finalized dossiers from finalized_index.json and exit.",
    )
    parser.add_argument("--model", default="gpt-5.2")
    parser.add_argument("--max-iterations", type=int, default=None)
    gp_group = parser.add_mutually_exclusive_group(required=False)
    gp_group.add_argument("--global-placement", action="store_true", dest="requires_global_placement")
    gp_group.add_argument("--no-global-placement", action="store_false", dest="requires_global_placement")
    rr_group = parser.add_mutually_exclusive_group(required=False)
    rr_group.add_argument("--render-required", action="store_true", dest="render_required")
    rr_group.add_argument("--no-render-required", action="store_false", dest="render_required")
    parser.set_defaults(requires_global_placement=None, render_required=None)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--no-live", action="store_true", help="Disable live agent tape output.")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Suppress live logs and print only final JSON snapshot.",
    )
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
    finalized_entries = _load_finalized_index_entries()
    if bool(args.list_finalized):
        _print_finalized_entries(finalized_entries, out=out)
        return 0

    dossier_id = args.dossier_id
    if bool(getattr(args, "right_of_way", False)):
        match = _select_finalized_entry(finalized_entries, query="right of way deed")
        if match is None:
            raise SystemExit("Could not find 'Right of Way Deed' in finalized_index.json.")
        dossier_id = str(match.get("dossier_id") or "")
        if not bool(args.json_only):
            out.write(f"[agent-loop] selected finalized dossier '{match.get('title')}' ({dossier_id})\n")
            out.flush()
    elif isinstance(getattr(args, "finalized_title", None), str) and args.finalized_title.strip():
        match = _select_finalized_entry(finalized_entries, query=args.finalized_title)
        if match is None:
            raise SystemExit(f"No finalized dossier matched title query: {args.finalized_title!r}")
        dossier_id = str(match.get("dossier_id") or "")
        if not bool(args.json_only):
            out.write(f"[agent-loop] selected finalized dossier '{match.get('title')}' ({dossier_id})\n")
            out.flush()

    text = _resolve_text(args.text, args.text_file)
    if not any([dossier_id, text, args.initial_ir_ref]):
        raise SystemExit(
            "Provide one of --dossier-id, --finalized-title, --right-of-way, --text-file, --text, or --initial-ir-ref."
        )

    request_kwargs: dict[str, Any] = {
        "dossier_id": dossier_id,
        "text": text,
        "initial_ir_ref": args.initial_ir_ref,
        "model": args.model,
        "max_iterations": args.max_iterations,
        "background": True,
    }
    if isinstance(args.requires_global_placement, bool):
        request_kwargs["requires_global_placement"] = args.requires_global_placement
    if isinstance(args.render_required, bool):
        request_kwargs["render_required"] = args.render_required

    request = agent_loop.AgentLoopRunRequest(
        **request_kwargs,
    )

    start = await agent_loop.start_agent_loop_run(request)
    run_id = str(start["run_id"])
    live_enabled = not bool(args.no_live or args.json_only)

    if live_enabled:
        out.write(f"[agent-loop] started run_id={run_id} status={start.get('status')} dossier_id={start.get('dossier_id')}\n")
        out.flush()

    queue = await agent_loop.event_bus.subscribe(run_id) if live_enabled else None
    event_task = (
        asyncio.create_task(_consume_events(run_id=run_id, q=queue, out=out))
        if queue is not None
        else None
    )

    final_snapshot: dict[str, Any] | None = None
    try:
        final_snapshot = await _poll_until_terminal(
            run_id=run_id,
            poll_interval=max(0.1, float(args.poll_interval)),
            out=out,
            live_enabled=live_enabled,
        )
    finally:
        if event_task is not None and queue is not None:
            event_task.cancel()
            try:
                await event_task
            except asyncio.CancelledError:
                pass
            try:
                await agent_loop.event_bus.unsubscribe(run_id, queue)
            except Exception:
                pass

    payload = final_snapshot or {"run_id": run_id, "status": "unknown"}
    out.write(json.dumps(payload, ensure_ascii=False, indent=2))
    out.write("\n")
    out.flush()

    status = str(payload.get("status") or "")
    terminal = payload.get("terminal") if isinstance(payload.get("terminal"), dict) else {}
    terminal_success = terminal.get("success")
    if status == "failed":
        return 1
    if isinstance(terminal_success, bool) and not terminal_success:
        return 2
    return 0


def _resolve_text(inline_text: str | None, text_file: str | None) -> str | None:
    if inline_text and inline_text.strip():
        return inline_text.strip()
    if text_file and text_file.strip():
        return Path(text_file).read_text(encoding="utf-8").strip()
    return None


def _load_finalized_index_entries() -> list[dict[str, Any]]:
    path = dossiers_state_root() / "finalized_index.json"
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(payload, dict):
        return []
    raw_entries = payload.get("finalized", [])
    if not isinstance(raw_entries, list):
        return []
    entries: list[dict[str, Any]] = []
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        did = item.get("dossier_id")
        if not isinstance(did, str) or not did.strip():
            continue
        entries.append(item)
    return entries


def _select_finalized_entry(entries: list[dict[str, Any]], *, query: str) -> dict[str, Any] | None:
    q = (query or "").strip().lower()
    if not q:
        return None
    exact_title_matches = [
        e for e in entries if isinstance(e.get("title"), str) and str(e.get("title")).strip().lower() == q
    ]
    if len(exact_title_matches) == 1:
        return exact_title_matches[0]
    contains_title_matches = [
        e for e in entries if isinstance(e.get("title"), str) and q in str(e.get("title")).strip().lower()
    ]
    if len(contains_title_matches) == 1:
        return contains_title_matches[0]
    if len(exact_title_matches) > 1:
        raise SystemExit(f"Ambiguous finalized title query {query!r}: multiple exact matches.")
    if len(contains_title_matches) > 1:
        titles = ", ".join(str(e.get("title") or e.get("dossier_id")) for e in contains_title_matches[:5])
        raise SystemExit(f"Ambiguous finalized title query {query!r}: {titles}")
    return None


def _print_finalized_entries(entries: list[dict[str, Any]], *, out: TextIO) -> None:
    if not entries:
        out.write("No finalized dossiers found in canonical finalized_index.json\n")
        out.flush()
        return
    out.write("Canonical finalized dossiers:\n")
    for idx, entry in enumerate(entries, start=1):
        did = str(entry.get("dossier_id") or "")
        title = str(entry.get("title") or "(untitled)")
        ts = str(entry.get("latest_generated_at") or "")
        has_errors = bool(entry.get("has_errors"))
        out.write(f"{idx}. {title} | dossier_id={did} | finalized_at={ts} | has_errors={str(has_errors).lower()}\n")
    out.flush()


async def _poll_until_terminal(
    *,
    run_id: str,
    poll_interval: float,
    out: TextIO,
    live_enabled: bool,
) -> dict[str, Any]:
    last_status: str | None = None
    while True:
        snapshot = await agent_loop.get_agent_loop_run(run_id)
        status = str(snapshot.get("status") or "unknown")
        if live_enabled and status != last_status:
            out.write(f"[agent-loop] run_id={run_id} status={status}\n")
            out.flush()
            last_status = status
        if status in {"completed", "failed"}:
            return snapshot
        await asyncio.sleep(poll_interval)


async def _consume_events(*, run_id: str, q: asyncio.Queue, out: TextIO) -> None:
    while True:
        data = await q.get()
        try:
            event = json.loads(data)
        except Exception:
            out.write(f"[agent-loop:event] {data}\n")
            out.flush()
            continue

        status = event.get("status") if isinstance(event, dict) else None
        if isinstance(status, dict):
            seq = event.get("seq")
            iteration = status.get("iteration")
            chip = status.get("status_chip")
            line1 = status.get("line1")
            line2 = status.get("line2")
            parts = [f"[agent-loop:tape] run_id={run_id}"]
            if isinstance(seq, int):
                parts.append(f"seq={seq}")
            if isinstance(iteration, int):
                parts.append(f"iter={iteration}")
            if chip:
                parts.append(f"chip={chip}")
            if line1:
                parts.append(f"{line1}")
            if line2:
                parts.append(f"| {line2}")
            out.write(" ".join(parts) + "\n")
            out.flush()
            continue

        event_type = event.get("event_type") if isinstance(event, dict) else None
        if event_type:
            out.write(f"[agent-loop:event] run_id={run_id} event_type={event_type}\n")
            out.flush()


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
