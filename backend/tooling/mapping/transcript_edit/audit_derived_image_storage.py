"""CLI entry point for the STORAGE-BR-004 derived image storage audit.

Usage::

    python -m tooling.mapping.transcript_edit.audit_derived_image_storage \\
        --dossier-id <id>

Prints a JSON report to stdout. Exits non-zero **only** on scope or argument errors
(``StorageAuditScopeError`` or argparse failures). Pixel mismatches, missing images, and
other audit findings are reported in the JSON body — they do not affect the exit code.

No ``--apply``, ``--delete``, ``--migrate``, or ``--repair`` flags: this tool is read-only.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .derived_image_storage_audit import StorageAuditScopeError, run_derived_image_storage_audit


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="audit_derived_image_storage",
        description=(
            "Audit transcript-edit derived image storage integrity (STORAGE-BR-004). "
            "Read-only: never modifies any file."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m tooling.mapping.transcript_edit.audit_derived_image_storage "
            "--dossier-id my_dossier\n"
            "  python -m tooling.mapping.transcript_edit.audit_derived_image_storage "
            "--all-dossiers --max-artifacts 200"
        ),
    )
    scope = p.add_argument_group("scope (at least one required)")
    scope.add_argument("--dossier-id", metavar="ID", help="Audit a single dossier.")
    scope.add_argument(
        "--all-dossiers",
        action="store_true",
        help="Audit every dossier found under the transcript-edit artifacts root.",
    )

    narrow = p.add_argument_group("optional scope narrowing")
    narrow.add_argument(
        "--transcription-id",
        metavar="ID",
        help="Restrict to a single transcription_id within the dossier.",
    )
    narrow.add_argument(
        "--workspace-id",
        metavar="ID",
        help="Restrict to a single workspace_id within the transcription.",
    )

    p.add_argument(
        "--harness-audit-root",
        dest="harness_audit_roots",
        action="append",
        metavar="DIR",
        help=(
            "Additional directory whose *.json files are scanned for derived-image ref "
            "appearances (may be repeated). No harness packages are imported."
        ),
    )

    bounds = p.add_argument_group("output bounds")
    bounds.add_argument(
        "--max-artifacts",
        type=int,
        default=500,
        metavar="N",
        help="Maximum artifact rows in the report (default: 500).",
    )
    bounds.add_argument(
        "--max-duplicate-groups",
        type=int,
        default=100,
        metavar="N",
        help="Maximum duplicate-group rows in the report (default: 100).",
    )
    bounds.add_argument(
        "--max-diagnostics",
        type=int,
        default=200,
        metavar="N",
        help="Maximum diagnostic entries in the report (default: 200).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    harness_roots: list[Path] | None = None
    if args.harness_audit_roots:
        harness_roots = [Path(r) for r in args.harness_audit_roots]

    try:
        report = run_derived_image_storage_audit(
            dossier_id=args.dossier_id or None,
            transcription_id=args.transcription_id or None,
            workspace_id=args.workspace_id or None,
            all_dossiers=args.all_dossiers,
            harness_audit_roots=harness_roots,
            max_artifacts=args.max_artifacts,
            max_duplicate_groups=args.max_duplicate_groups,
            max_diagnostics=args.max_diagnostics,
        )
    except StorageAuditScopeError as exc:
        print(
            json.dumps({"error": exc.code, "message": exc.message}, indent=2),
            file=sys.stderr,
        )
        return 2

    print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
