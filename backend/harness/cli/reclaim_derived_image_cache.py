"""Operator CLI: quiescence-gated derived-image PNG cache reclamation (STORAGE-BR-010)."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from harness.cli.fork_spawn_argv import LAUNCH_CONTEXT_JSON_FLAG
from harness.cli.run_quiescence import assess_run_quiescence
from harness.cli.run_state import read_state
from tooling.mapping.transcript_edit.derived_image_reclamation_apply import (
    REASON_RUN_SCOPE_UNKNOWN,
    apply_derived_image_reclamation,
)

_REQUIRED_DOMAIN_ID = "transcript_edit"


def _parse_launch_context(spawn_argv: list[str]) -> dict[str, Any] | None:
    argv = list(spawn_argv or [])
    for index, arg in enumerate(argv):
        if arg == LAUNCH_CONTEXT_JSON_FLAG and index + 1 < len(argv):
            try:
                doc = json.loads(argv[index + 1])
            except json.JSONDecodeError:
                return None
            return doc if isinstance(doc, dict) else None
        prefix = f"{LAUNCH_CONTEXT_JSON_FLAG}="
        if arg.startswith(prefix):
            try:
                doc = json.loads(arg[len(prefix) :])
            except json.JSONDecodeError:
                return None
            return doc if isinstance(doc, dict) else None
    return None


def _domain_id_from_spawn_argv(spawn_argv: list[str]) -> str | None:
    argv = list(spawn_argv or [])
    for index, arg in enumerate(argv):
        if type(arg) is not str:
            continue
        if arg == "--domain-id" and index + 1 < len(argv):
            value = argv[index + 1]
            return value if type(value) is str else None
        prefix = "--domain-id="
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return None


def _nonblank_str(value: Any) -> str | None:
    if type(value) is not str:
        return None
    text = value.strip()
    return text or None


def resolve_reclamation_scope_from_run(run_id: str) -> tuple[dict[str, Any] | None, str | None]:
    """Recover dossier/workspace scope from registered harness run launch arguments."""
    if type(run_id) is not str:
        return None, REASON_RUN_SCOPE_UNKNOWN
    rid = run_id.strip()
    if not rid:
        return None, REASON_RUN_SCOPE_UNKNOWN
    state = read_state(rid)
    if state is None:
        return None, REASON_RUN_SCOPE_UNKNOWN
    if _domain_id_from_spawn_argv(state.spawn_argv) != _REQUIRED_DOMAIN_ID:
        return None, REASON_RUN_SCOPE_UNKNOWN
    launch = _parse_launch_context(state.spawn_argv)
    if not isinstance(launch, dict):
        return None, REASON_RUN_SCOPE_UNKNOWN

    dossier_id = _nonblank_str(launch.get("dossier_id"))
    if dossier_id is None:
        return None, REASON_RUN_SCOPE_UNKNOWN

    raw_workspace = launch.get("workspace_id")
    if raw_workspace is None:
        workspace_id = rid
    else:
        workspace_id = _nonblank_str(raw_workspace)
        if workspace_id is None:
            return None, REASON_RUN_SCOPE_UNKNOWN

    raw_tx = launch.get("transcription_id")
    if raw_tx is None:
        transcription_id = None
    else:
        transcription_id = _nonblank_str(raw_tx)
        if transcription_id is None:
            return None, REASON_RUN_SCOPE_UNKNOWN

    return (
        {
            "run_id": rid,
            "dossier_id": dossier_id,
            "transcription_id": transcription_id,
            "workspace_id": workspace_id,
        },
        None,
    )


def reclaim_derived_image_cache(
    *,
    run_id: str,
    apply: bool = False,
    max_deletions: int = 100,
) -> dict[str, Any]:
    scope, err = resolve_reclamation_scope_from_run(run_id)
    if err or scope is None:
        return {
            "schema_version": "transcript_edit.derived_image_reclamation_apply.v1",
            "authorization_posture": "operator_apply_required",
            "apply": apply if type(apply) is bool else False,
            "status": "refused",
            "reason_code": err or REASON_RUN_SCOPE_UNKNOWN,
            "scope": {
                "run_id": run_id if type(run_id) is str else None,
                "dossier_id": None,
                "transcription_id": None,
                "workspace_id": None,
            },
            "eligible_count": 0,
            "eligible_bytes": 0,
            "selected_count": 0,
            "not_selected_count": 0,
            "deleted_count": 0,
            "bytes_reclaimed": 0,
            "skipped_count": 0,
            "aborted_count": 0,
            "artifacts": [],
            "artifacts_omitted_count": 0,
        }

    quiescence_fn = None
    if apply:
        rid = scope["run_id"]
        quiescence_fn = lambda: assess_run_quiescence(rid)  # noqa: E731

    return apply_derived_image_reclamation(
        dossier_id=scope["dossier_id"],
        workspace_id=scope["workspace_id"],
        transcription_id=scope.get("transcription_id"),
        apply=apply,
        max_deletions=max_deletions,
        quiescence_fn=quiescence_fn,
        run_id=scope["run_id"],
    )


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, allow_nan=False))
    sys.stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness.cli.reclaim_derived_image_cache",
        description=(
            "Plan or apply reconstructible derived-image PNG cache reclamation for one "
            "harness run workspace. Default is dry-run; --apply mutates PNG cache only."
        ),
    )
    parser.add_argument("--run-id", required=True, help="Exact harness CLI run id.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete eligible PNG cache bytes after quiescence checks.",
    )
    parser.add_argument(
        "--max-deletions",
        type=int,
        default=100,
        metavar="N",
        help="Maximum PNG deletions per invocation (default: 100).",
    )
    args = parser.parse_args(argv)
    result = reclaim_derived_image_cache(
        run_id=args.run_id.strip(),
        apply=bool(args.apply),
        max_deletions=args.max_deletions,
    )
    _print_json(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
