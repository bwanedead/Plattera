"""CLI runner for controller-driven kernel sessions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from time import time
from typing import Sequence, TextIO

from agent_kernel.models import KernelBudgets, KernelGoal, KernelSessionStartRequest
from services.agent_kernel.run_artifact_persistence_service import RunArtifactPersistenceService

from .controller import run_controller_loop
from .openai_client import OpenAINextStepClient
from .bootstrap import persist_deed_text_artifact
from feature_graph.kernel_executor_composition import build_plattera_default_kernel_session_manager


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-controller-loop",
        description="Run the LLM-driven controller loop against the step-driven kernel.",
    )
    bootstrap = parser.add_mutually_exclusive_group(required=False)
    bootstrap.add_argument("--dossier-id", dest="dossier_id")
    bootstrap.add_argument("--text-file", dest="text_file")
    bootstrap.add_argument("--text", dest="text")
    parser.add_argument("--request-id", dest="request_id")
    parser.add_argument("--initial-ir-ref", dest="initial_ir_ref")
    parser.add_argument("--model", default="gpt-5-mini")
    parser.add_argument("--max-iterations", type=int, default=12)
    parser.add_argument("--global-placement", action="store_true")
    parser.add_argument("--render-required", action="store_true")
    return parser


def run_cli(argv: Sequence[str] | None = None, stdout: TextIO | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    request_id = args.request_id or f"controller-{int(time())}"
    deed_text = _resolve_deed_text(args.text, args.text_file)
    initial_graph_json = _build_bootstrap_graph(
        request_id=request_id,
        dossier_id=args.dossier_id,
        deed_text=deed_text,
    )
    start_request = KernelSessionStartRequest(
        request_id=request_id,
        goal=KernelGoal(
            requires_global_placement=bool(args.global_placement),
            render_required=bool(args.render_required),
            objective="controller_cli_run",
        ),
        budgets=KernelBudgets(
            max_steps=30,
            max_wall_time_seconds=600,
            max_retrieval_calls=12,
            max_semantic_calls=8,
            max_patch_calls=8,
        ),
        dossier_id=args.dossier_id,
        source_entry_ref=(f"final:{args.dossier_id}" if args.dossier_id else None),
        initial_ir_ref=args.initial_ir_ref,
        initial_graph_json=initial_graph_json,
    )

    persistence = RunArtifactPersistenceService()
    session_manager = build_plattera_default_kernel_session_manager(persistence_service=persistence)
    llm_client = OpenAINextStepClient()
    result = run_controller_loop(
        session_manager=session_manager,
        llm_client=llm_client,
        start_request=start_request,
        model=args.model,
        max_iterations=max(1, int(args.max_iterations)),
    )
    sink = stdout or sys.stdout
    sink.write(
        json.dumps(
            {
                "request_id": request_id,
                "session_id": result.session_id,
                "run_artifact_ref": result.run_artifact_ref,
                "transcript_artifact_ref": result.transcript_artifact_ref,
                "terminal": result.terminal.model_dump(mode="json"),
                "iterations": result.iterations,
                "dashboard": result.last_dashboard,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    sink.write("\n")
    return 0


def _resolve_deed_text(inline_text: str | None, text_file: str | None) -> str | None:
    if inline_text and inline_text.strip():
        return inline_text.strip()
    if text_file and text_file.strip():
        return Path(text_file).read_text(encoding="utf-8").strip()
    return None


def _build_bootstrap_graph(
    *,
    request_id: str,
    dossier_id: str | None,
    deed_text: str | None,
) -> dict[str, object] | None:
    if not deed_text:
        return None
    deed_artifact = persist_deed_text_artifact(
        request_id=request_id,
        deed_text=deed_text,
        dossier_id=dossier_id,
    )
    return {
        "graph_id": f"graph_{request_id}",
        "nodes": [],
        "edges": [],
        "metadata": {
            "dossier_id": dossier_id,
            "source": "controller_cli_text_bootstrap",
            "deed_text_excerpt": deed_artifact.excerpt,
            "deed_text_artifact_ref": deed_artifact.artifact_path,
        },
    }


def main() -> None:
    raise SystemExit(run_cli())


if __name__ == "__main__":
    main()
