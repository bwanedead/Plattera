"""Freeze a dossier T0 baseline into an immutable local practice fixture packet.

Thin CLI: parse inputs, call ``harness.fixtures.dossier_t0_fixture``, report JSON.
No ``--force`` / overwrite mode.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from harness.fixtures.dossier_t0_fixture import (
    DossierT0FixtureError,
    FreezePlan,
    SegmentSpec,
    freeze_dossier_t0_fixture,
    write_fixture_set_manifest,
)


def _print_json(obj: dict[str, Any]) -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _parse_segment(raw: str) -> SegmentSpec:
    """Parse POSITION|TRANSCRIPTION_ID|SOURCE_IMAGE_PATH|SHA256|SOURCE_FIXTURE_NAME."""
    parts = str(raw).split("|")
    if len(parts) != 5:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_segment_arg",
            "expected POSITION|TRANSCRIPTION_ID|SOURCE_IMAGE_PATH|SHA256|SOURCE_FIXTURE_NAME",
        )
    position_text, transcription_id, source_path, sha256, fixture_name = parts
    try:
        position = int(position_text)
    except ValueError as exc:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_segment_arg",
            f"position must be int, got {position_text!r}",
        ) from exc
    return SegmentSpec(
        position=position,
        transcription_id=transcription_id.strip(),
        source_image_path=Path(source_path.strip()),
        source_sha256=sha256.strip().lower(),
        source_fixture_name=fixture_name.strip(),
    )


def build_plan_from_args(args: argparse.Namespace) -> FreezePlan:
    segments = tuple(_parse_segment(item) for item in args.segment)
    return FreezePlan(
        dossiers_root=Path(args.dossiers_root),
        destination_root=Path(args.destination_root),
        fixture_id=str(args.fixture_id).strip(),
        dossier_id=str(args.dossier_id).strip(),
        segments=segments,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="harness.cli.freeze_dossier_t0_fixture",
        description="Freeze allowlisted dossier T0 artifacts into an immutable practice fixture.",
    )
    parser.add_argument("--dossiers-root", required=True, help="Explicit dossiers_data root.")
    parser.add_argument(
        "--destination-root",
        required=True,
        help="Parent directory that will contain <fixture-id>/.",
    )
    parser.add_argument("--fixture-id", required=True)
    parser.add_argument("--dossier-id", required=True)
    parser.add_argument(
        "--segment",
        action="append",
        required=True,
        help=(
            "Repeatable segment spec: "
            "POSITION|TRANSCRIPTION_ID|SOURCE_IMAGE_PATH|SHA256|SOURCE_FIXTURE_NAME"
        ),
    )
    parser.add_argument(
        "--write-set-manifest",
        action="store_true",
        help=(
            "After a successful freeze, rewrite fixture_set_manifest.json under destination-root "
            "listing every sibling */fixture_manifest.json (no dependency claims)."
        ),
    )
    args = parser.parse_args(argv)

    try:
        plan = build_plan_from_args(args)
        result = freeze_dossier_t0_fixture(plan)
        set_manifest_path = None
        if args.write_set_manifest:
            destination_root = Path(args.destination_root)
            fixture_ids = sorted(
                path.parent.name
                for path in destination_root.glob("*/fixture_manifest.json")
                if path.is_file()
            )
            set_manifest_path = str(
                write_fixture_set_manifest(
                    destination_root=destination_root,
                    fixture_ids=fixture_ids,
                )
            )
        payload: dict[str, Any] = {
            "status": "ok",
            "fixture_id": result.fixture_id,
            "dossier_id": result.dossier_id,
            "manifest_path": str(result.manifest_path),
            "segment_count": result.segment_count,
            "outcome": result.outcome,
            "copied_file_count": result.copied_file_count,
            "created": result.outcome == "created",
            "idempotent_replay": result.outcome == "idempotent_replay",
        }
        if set_manifest_path is not None:
            payload["fixture_set_manifest_path"] = set_manifest_path
        _print_json(payload)
        return 0
    except DossierT0FixtureError as exc:
        _print_json(
            {
                "status": "error",
                "reason": exc.reason,
                "detail": exc.detail,
            }
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
