"""CLI entry point for STORAGE-BR-009 derived-image reclamation planning.

Usage::

    python -m tooling.mapping.transcript_edit.plan_derived_image_reclamation \\
        --dossier-id <id>

Read-only: never modifies any file. No ``--apply``, delete, or confirmation bypass.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .derived_image_reclamation_plan import run_derived_image_reclamation_plan
from .derived_image_storage_audit import StorageAuditScopeError


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="plan_derived_image_reclamation",
        description=(
            "Plan reconstructible derived-image PNG cache reclamation (STORAGE-BR-009). "
            "Read-only planning: never authorizes deletion."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m tooling.mapping.transcript_edit.plan_derived_image_reclamation "
            "--dossier-id my_dossier\n"
            "  python -m tooling.mapping.transcript_edit.plan_derived_image_reclamation "
            "--all-dossiers --max-candidates 100"
        ),
    )
    scope = p.add_argument_group("scope (at least one required)")
    scope.add_argument("--dossier-id", metavar="ID", help="Plan within a single dossier.")
    scope.add_argument(
        "--all-dossiers",
        action="store_true",
        help="Plan across every dossier under the transcript-edit artifacts root.",
    )

    narrow = p.add_argument_group("optional scope narrowing")
    narrow.add_argument("--transcription-id", metavar="ID")
    narrow.add_argument("--workspace-id", metavar="ID")

    p.add_argument(
        "--harness-audit-root",
        dest="harness_audit_roots",
        action="append",
        metavar="DIR",
        help="Additional directory scanned for derived-image ref appearances.",
    )

    bounds = p.add_argument_group("output bounds")
    bounds.add_argument(
        "--max-candidates",
        type=int,
        default=500,
        metavar="N",
        help="Maximum candidate detail rows (default: 500).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    harness_roots: list[Path] | None = None
    if args.harness_audit_roots:
        harness_roots = [Path(r) for r in args.harness_audit_roots]

    try:
        plan = run_derived_image_reclamation_plan(
            dossier_id=args.dossier_id or None,
            transcription_id=args.transcription_id or None,
            workspace_id=args.workspace_id or None,
            all_dossiers=args.all_dossiers,
            harness_audit_roots=harness_roots,
            max_candidates=args.max_candidates,
        )
    except StorageAuditScopeError as exc:
        print(
            json.dumps({"error": exc.code, "message": exc.message}, indent=2),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
