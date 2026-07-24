"""Generic dossier T0 practice-fixture freeze tooling.

Public contracts and freeze orchestration. Manifest schema/validation lives in
``dossier_t0_fixture_manifest``. Explicit roots only — no production path defaults.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from harness.fixtures.dossier_t0_fixture_manifest import (
    CONFLICT_REASON,
    MANIFEST_NAME,
    SET_MANIFEST_NAME,
    DossierT0FixtureError,
    build_manifest,
    build_set_manifest_payload,
    canonical_json_text,
    file_fingerprint,
    is_hex_sha256,
    require_strict_int,
    sha256_file,
    validate_fixture_dir,
    validate_set_manifest_payload,
    write_json,
)

# Re-exports for callers/tests.
__all__ = [
    "CONFLICT_REASON",
    "MANIFEST_NAME",
    "SET_MANIFEST_NAME",
    "DossierT0FixtureError",
    "FreezePlan",
    "FreezeResult",
    "SegmentSpec",
    "file_fingerprint",
    "freeze_dossier_t0_fixture",
    "sha256_file",
    "validate_fixture_integrity",
    "write_fixture_set_manifest",
]


@dataclass(frozen=True)
class SegmentSpec:
    """One ordered segment to freeze from a source dossier."""

    position: int
    transcription_id: str
    source_image_path: Path
    source_sha256: str
    source_fixture_name: str


@dataclass(frozen=True)
class FreezePlan:
    """Explicit freeze coordinates for one dossier T0 fixture packet."""

    dossiers_root: Path
    destination_root: Path
    fixture_id: str
    dossier_id: str
    segments: tuple[SegmentSpec, ...]


@dataclass(frozen=True)
class FreezeResult:
    fixture_id: str
    dossier_id: str
    fixture_dir: Path
    manifest_path: Path
    segment_count: int
    outcome: str  # "created" | "idempotent_replay"
    copied_file_count: int


def freeze_dossier_t0_fixture(plan: FreezePlan) -> FreezeResult:
    """Freeze or idempotently replay a dossier T0 fixture packet."""
    _validate_freeze_plan(plan)
    fixture_dir = (plan.destination_root / plan.fixture_id).resolve()
    if fixture_dir.exists():
        return _replay_existing(plan, fixture_dir)

    associations = _load_associations(plan.dossiers_root, plan.dossier_id)
    _validate_segment_order_against_associations(plan, associations)
    _validate_provenance_hashes(plan, associations)

    staging_dir = _staging_path(plan.destination_root, plan.fixture_id)
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=False)

    try:
        copied_paths = _materialize_packet(plan, associations, staging_dir)
        assoc_by_tid = {str(a["transcription_id"]): a for a in associations}
        manifest = build_manifest(
            fixture_id=plan.fixture_id,
            dossier_id=plan.dossier_id,
            segments=plan.segments,
            associations_by_tid=assoc_by_tid,
            staging_dir=staging_dir,
            copied_paths=copied_paths,
        )
        write_json(staging_dir / MANIFEST_NAME, manifest)
        validate_fixture_dir(staging_dir, expected_plan=plan)
        plan.destination_root.mkdir(parents=True, exist_ok=True)
        staging_dir.replace(fixture_dir)
    except Exception:
        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    return FreezeResult(
        fixture_id=plan.fixture_id,
        dossier_id=plan.dossier_id,
        fixture_dir=fixture_dir,
        manifest_path=fixture_dir / MANIFEST_NAME,
        segment_count=len(plan.segments),
        outcome="created",
        copied_file_count=len(copied_paths),
    )


def validate_fixture_integrity(fixture_dir: Path) -> dict[str, Any]:
    """Validate an existing fixture packet; return its normalized manifest."""
    return validate_fixture_dir(Path(fixture_dir), expected_plan=None)


def write_fixture_set_manifest(
    *,
    destination_root: Path,
    fixture_ids: Sequence[str],
) -> Path:
    """Write a set listing of fixture manifests without dependency claims.

    Idempotent: if the canonical payload already exists on disk, perform no write.
    Each member fixture packet is validated before inclusion.
    """
    root = Path(destination_root).resolve()
    payload = build_set_manifest_payload(fixture_ids)
    validate_set_manifest_payload(payload)

    for member in payload["fixtures"]:
        fid = str(member["fixture_id"])
        manifest_ref = str(member["manifest_ref"])
        if manifest_ref != f"{fid}/{MANIFEST_NAME}":
            raise DossierT0FixtureError(
                "dossier_t0_fixture_set_member_ref_mismatch",
                f"expected {fid}/{MANIFEST_NAME}, got {manifest_ref}",
            )
        member_dir = (root / fid).resolve()
        try:
            member_dir.relative_to(root)
        except ValueError as exc:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_set_path_escape",
                fid,
            ) from exc
        if not (member_dir / MANIFEST_NAME).is_file():
            raise DossierT0FixtureError(
                "dossier_t0_fixture_set_missing_member",
                f"missing {manifest_ref}",
            )
        validate_fixture_dir(member_dir, expected_plan=None)

    out = root / SET_MANIFEST_NAME
    canonical = canonical_json_text(payload)
    if out.is_file() and out.read_text(encoding="utf-8") == canonical:
        return out
    root.mkdir(parents=True, exist_ok=True)
    write_json(out, payload)
    return out


def _validate_freeze_plan(plan: FreezePlan) -> None:
    if not isinstance(plan, FreezePlan):
        raise DossierT0FixtureError("dossier_t0_fixture_invalid_plan", "plan must be FreezePlan")
    _require_token(plan.fixture_id, field="fixture_id")
    _require_token(plan.dossier_id, field="dossier_id")
    if not plan.segments:
        raise DossierT0FixtureError("dossier_t0_fixture_invalid_plan", "segments required")

    dossiers_root = Path(plan.dossiers_root)
    destination_root = Path(plan.destination_root)
    if not dossiers_root.is_dir():
        raise DossierT0FixtureError(
            "dossier_t0_fixture_missing_dossiers_root",
            str(dossiers_root),
        )

    positions: set[int] = set()
    transcription_ids: set[str] = set()
    fixture_names: set[str] = set()
    for segment in plan.segments:
        if not isinstance(segment, SegmentSpec):
            raise DossierT0FixtureError(
                "dossier_t0_fixture_invalid_segment",
                "segment must be SegmentSpec",
            )
        position = require_strict_int(
            segment.position,
            reason="dossier_t0_fixture_invalid_segment",
            detail=f"position must be positive int, got {segment.position!r}",
            positive=True,
        )
        if position in positions:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_duplicate_position",
                str(position),
            )
        positions.add(position)

        tid = _require_token(segment.transcription_id, field="transcription_id")
        if tid in transcription_ids:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_duplicate_transcription_id",
                tid,
            )
        transcription_ids.add(tid)

        name = str(segment.source_fixture_name or "").strip().replace("\\", "/")
        if not name or "/" in name or name in {".", ".."}:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_invalid_source_fixture_name",
                repr(segment.source_fixture_name),
            )
        if name in fixture_names:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_duplicate_source_fixture_name",
                name,
            )
        fixture_names.add(name)

        source_path = Path(segment.source_image_path)
        if not source_path.is_file():
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_source_image",
                str(source_path),
            )
        expected = str(segment.source_sha256 or "").strip().lower()
        if not is_hex_sha256(expected):
            raise DossierT0FixtureError(
                "dossier_t0_fixture_invalid_source_sha256",
                repr(segment.source_sha256),
            )
        actual = sha256_file(source_path)
        if actual != expected:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_source_hash_mismatch",
                f"{source_path}: expected {expected}, got {actual}",
            )

    ordered_positions = [s.position for s in plan.segments]
    if ordered_positions != sorted(ordered_positions):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_segment_order",
            "segments must be listed in ascending position order",
        )

    if destination_root.exists() and not destination_root.is_dir():
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_destination_root",
            str(destination_root),
        )


def _require_token(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise DossierT0FixtureError("dossier_t0_fixture_invalid_plan", f"{field} required")
    if any(ch in text for ch in ("/", "\\")) or ".." in text or text in {".", ".."}:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_plan",
            f"{field} must be a single path segment, got {text!r}",
        )
    return text


def _associations_path(dossiers_root: Path, dossier_id: str) -> Path:
    return Path(dossiers_root) / "associations" / f"assoc_{dossier_id}.json"


def _transcription_root(dossiers_root: Path, dossier_id: str, transcription_id: str) -> Path:
    return Path(dossiers_root) / "views" / "transcriptions" / dossier_id / transcription_id


def _load_associations(dossiers_root: Path, dossier_id: str) -> list[dict[str, Any]]:
    path = _associations_path(dossiers_root, dossier_id)
    if not path.is_file():
        raise DossierT0FixtureError(
            "dossier_t0_fixture_missing_associations",
            str(path),
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_associations",
            f"{path}: {exc}",
        ) from exc
    if not isinstance(payload, dict):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_associations",
            "root must be object",
        )
    raw = payload.get("associations")
    if not isinstance(raw, list) or not raw:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_associations",
            "associations must be a non-empty list",
        )
    entries: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise DossierT0FixtureError(
                "dossier_t0_fixture_malformed_associations",
                "association entry must be object",
            )
        tid = item.get("transcription_id")
        position = item.get("position")
        if not isinstance(tid, str) or not tid.strip():
            raise DossierT0FixtureError(
                "dossier_t0_fixture_malformed_associations",
                "transcription_id required",
            )
        try:
            require_strict_int(
                position,
                reason="dossier_t0_fixture_malformed_associations",
                detail=f"invalid position for {tid}",
                positive=True,
            )
        except DossierT0FixtureError:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_malformed_associations",
                f"invalid position for {tid}",
            ) from None
        entries.append(item)
    return sorted(entries, key=lambda e: int(e["position"]))


def _validate_segment_order_against_associations(
    plan: FreezePlan,
    associations: Sequence[Mapping[str, Any]],
) -> None:
    assoc_seq = [(int(a["position"]), str(a["transcription_id"])) for a in associations]
    if len(assoc_seq) != len({position for position, _tid in assoc_seq}):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_associations",
            "duplicate association positions",
        )
    planned = [(s.position, s.transcription_id) for s in plan.segments]
    if planned != assoc_seq:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_segment_order_mismatch",
            "planned segments must match association order",
        )


def _provenance_source_hash(association: Mapping[str, Any], *, transcription_id: str) -> str:
    metadata = association.get("metadata")
    if not isinstance(metadata, dict):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_missing_provenance_hash",
            transcription_id,
        )
    provenance = metadata.get("provenance")
    if provenance is None:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_missing_provenance_hash",
            transcription_id,
        )
    if not isinstance(provenance, dict):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_provenance_hash",
            transcription_id,
        )
    source = provenance.get("source")
    if source is None:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_missing_provenance_hash",
            transcription_id,
        )
    if not isinstance(source, dict):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_provenance_hash",
            transcription_id,
        )
    file_hash = source.get("file_hash")
    if file_hash is None:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_missing_provenance_hash",
            transcription_id,
        )
    if not isinstance(file_hash, str) or not is_hex_sha256(file_hash.strip().lower()):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_provenance_hash",
            transcription_id,
        )
    return file_hash.strip().lower()


def _validate_provenance_hashes(
    plan: FreezePlan,
    associations: Sequence[Mapping[str, Any]],
) -> None:
    by_tid = {str(a["transcription_id"]): a for a in associations}
    for segment in plan.segments:
        association = by_tid[segment.transcription_id]
        provenance_hash = _provenance_source_hash(
            association, transcription_id=segment.transcription_id
        )
        planned = segment.source_sha256.strip().lower()
        if provenance_hash != planned:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_provenance_hash_mismatch",
                (
                    f"{segment.transcription_id}: provenance={provenance_hash} "
                    f"planned={planned}"
                ),
            )


def _staging_path(destination_root: Path, fixture_id: str) -> Path:
    parent = Path(destination_root)
    parent.mkdir(parents=True, exist_ok=True)
    return parent / f".{fixture_id}.__building__.{uuid.uuid4().hex}"


def _materialize_packet(
    plan: FreezePlan,
    associations: Sequence[Mapping[str, Any]],
    staging_dir: Path,
) -> list[Path]:
    assoc_by_tid = {str(a["transcription_id"]): a for a in associations}
    copied: list[Path] = []
    source_dir = staging_dir / "source"
    t0_dir = staging_dir / "t0"
    source_dir.mkdir(parents=True, exist_ok=True)
    t0_dir.mkdir(parents=True, exist_ok=True)

    for segment in plan.segments:
        if segment.transcription_id not in assoc_by_tid:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_transcription",
                segment.transcription_id,
            )
        tx_root = _transcription_root(
            plan.dossiers_root, plan.dossier_id, segment.transcription_id
        )
        if not tx_root.is_dir():
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_transcription",
                str(tx_root),
            )

        dest_source = source_dir / segment.source_fixture_name
        shutil.copy2(segment.source_image_path, dest_source)
        copied.append(dest_source)

        dest_tx = t0_dir / segment.transcription_id
        dest_tx.mkdir(parents=True, exist_ok=True)

        run_src = tx_root / "run.json"
        if not run_src.is_file():
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_t0_run",
                str(run_src),
            )
        run_dest = dest_tx / "run.json"
        shutil.copy2(run_src, run_dest)
        copied.append(run_dest)

        head_src = tx_root / "head.json"
        if head_src.is_file():
            head_dest = dest_tx / "head.json"
            shutil.copy2(head_src, head_dest)
            copied.append(head_dest)

        raw_src = tx_root / "raw"
        raw_dest = dest_tx / "raw"
        raw_dest.mkdir(parents=True, exist_ok=True)
        raw_copied = 0
        if raw_src.is_dir():
            for child in sorted(raw_src.iterdir()):
                if not child.is_file():
                    continue
                if child.suffix.lower() != ".json":
                    continue
                target = raw_dest / child.name
                shutil.copy2(child, target)
                copied.append(target)
                raw_copied += 1
        if raw_copied < 1:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_t0_raw",
                segment.transcription_id,
            )

    return copied


def _replay_existing(plan: FreezePlan, fixture_dir: Path) -> FreezeResult:
    try:
        manifest = validate_fixture_dir(fixture_dir, expected_plan=plan)
    except DossierT0FixtureError as exc:
        if exc.reason.startswith("dossier_t0_fixture_"):
            raise DossierT0FixtureError(CONFLICT_REASON, exc.detail or str(exc)) from exc
        raise
    return FreezeResult(
        fixture_id=plan.fixture_id,
        dossier_id=plan.dossier_id,
        fixture_dir=fixture_dir,
        manifest_path=fixture_dir / MANIFEST_NAME,
        segment_count=len(plan.segments),
        outcome="idempotent_replay",
        copied_file_count=len(manifest.get("files") or []),
    )
