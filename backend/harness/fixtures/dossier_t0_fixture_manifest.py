"""Manifest build/validate for dossier T0 practice fixtures.

Owns schema constants, path/ref integrity, typed manifest contracts, and
packet allowlist completeness. No freeze orchestration or storage copying.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "dossier_t0_fixture.v1"
SET_SCHEMA_VERSION = "dossier_t0_fixture_set.v1"
MANIFEST_NAME = "fixture_manifest.json"
SET_MANIFEST_NAME = "fixture_set_manifest.json"
CONFLICT_REASON = "dossier_t0_fixture_conflict"

_MANIFEST_KEYS = frozenset(
    {"schema_version", "fixture_id", "dossier_id", "segments", "files"}
)
_SEGMENT_KEYS = frozenset(
    {
        "position",
        "transcription_id",
        "source_ref",
        "source_sha256",
        "t0_run_ref",
        "t0_head_ref",
        "t0_raw_refs",
        "model",
        "extraction_mode",
        "redundancy_count",
    }
)
_FILE_KEYS = frozenset({"ref", "sha256", "byte_length"})
_SET_MANIFEST_KEYS = frozenset({"schema_version", "fixtures"})
_SET_MEMBER_KEYS = frozenset({"fixture_id", "manifest_ref"})


class DossierT0FixtureError(Exception):
    """Mechanical freeze/validation failure with a stable reason code."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = str(reason)
        self.detail = str(detail or "")
        message = self.reason if not self.detail else f"{self.reason}: {self.detail}"
        super().__init__(message)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_fingerprint(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    total = 0
    with Path(path).open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    return {"sha256": digest.hexdigest(), "byte_length": total}


def is_hex_sha256(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    if len(value) != 64:
        return False
    return all(c in "0123456789abcdef" for c in value)


def require_hex_sha256(value: Any, *, reason: str, detail: str = "") -> str:
    if not isinstance(value, str) or not is_hex_sha256(value):
        raise DossierT0FixtureError(reason, detail or repr(value))
    return value


def require_strict_int(
    value: Any,
    *,
    reason: str,
    detail: str = "",
    positive: bool = False,
) -> int:
    if type(value) is not int:
        raise DossierT0FixtureError(reason, detail or repr(value))
    if positive and value < 1:
        raise DossierT0FixtureError(reason, detail or repr(value))
    if not positive and value < 0:
        raise DossierT0FixtureError(reason, detail or repr(value))
    return value


def require_nonblank_str(value: Any, *, reason: str, detail: str = "") -> str:
    if not isinstance(value, str) or not value.strip():
        raise DossierT0FixtureError(reason, detail or repr(value))
    if value != value.strip():
        raise DossierT0FixtureError(reason, detail or repr(value))
    return value


def assert_safe_ref(ref: Any) -> str:
    if not isinstance(ref, str) or not ref.strip():
        raise DossierT0FixtureError("dossier_t0_fixture_invalid_ref", repr(ref))
    text = ref.replace("\\", "/")
    if text != ref:
        raise DossierT0FixtureError("dossier_t0_fixture_invalid_ref", ref)
    if text.startswith("/") or (len(text) >= 3 and text[1] == ":"):
        raise DossierT0FixtureError("dossier_t0_fixture_absolute_path", ref)
    parts = text.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise DossierT0FixtureError("dossier_t0_fixture_path_traversal", ref)
    return text


def assert_no_host_paths(value: Any) -> None:
    if isinstance(value, dict):
        for item in value.values():
            assert_no_host_paths(item)
        return
    if isinstance(value, list):
        for item in value:
            assert_no_host_paths(item)
        return
    if isinstance(value, str):
        text = value.replace("\\", "/")
        if text.startswith("/") or (len(text) >= 3 and text[1] == ":"):
            raise DossierT0FixtureError("dossier_t0_fixture_absolute_path", value)
        if ".." in text.split("/"):
            raise DossierT0FixtureError("dossier_t0_fixture_path_traversal", value)


def fixture_rel(root: Path, path: Path) -> str:
    rel = Path(path).resolve().relative_to(Path(root).resolve())
    return rel.as_posix()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=path.name, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)


def canonical_json_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def processing_params(
    association: Mapping[str, Any],
    run_path: Path,
) -> dict[str, Any]:
    metadata = association.get("metadata")
    if isinstance(metadata, dict):
        params = metadata.get("processing_params")
        if isinstance(params, dict) and params:
            return params
    if run_path.is_file():
        try:
            run_payload = json.loads(run_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            run_payload = {}
        if isinstance(run_payload, dict):
            params = run_payload.get("processing_params")
            if isinstance(params, dict):
                return params
    return {}


def require_processing_fields(params: Mapping[str, Any], *, transcription_id: str) -> dict[str, Any]:
    model = require_nonblank_str(
        params.get("model"),
        reason="dossier_t0_fixture_invalid_processing_params",
        detail=f"{transcription_id}: model",
    )
    extraction_mode = require_nonblank_str(
        params.get("extraction_mode"),
        reason="dossier_t0_fixture_invalid_processing_params",
        detail=f"{transcription_id}: extraction_mode",
    )
    redundancy_count = require_strict_int(
        params.get("redundancy_count"),
        reason="dossier_t0_fixture_invalid_processing_params",
        detail=f"{transcription_id}: redundancy_count",
        positive=True,
    )
    return {
        "model": model,
        "extraction_mode": extraction_mode,
        "redundancy_count": redundancy_count,
    }


def build_manifest(
    *,
    fixture_id: str,
    dossier_id: str,
    segments: Sequence[Any],
    associations_by_tid: Mapping[str, Mapping[str, Any]],
    staging_dir: Path,
    copied_paths: Sequence[Path],
) -> dict[str, Any]:
    segments_out: list[dict[str, Any]] = []
    files_out: list[dict[str, Any]] = []
    seen_refs: set[str] = set()

    for path in copied_paths:
        rel = fixture_rel(staging_dir, path)
        assert_safe_ref(rel)
        if rel in seen_refs:
            raise DossierT0FixtureError("dossier_t0_fixture_duplicate_ref", rel)
        seen_refs.add(rel)
        fp = file_fingerprint(path)
        files_out.append(
            {"ref": rel, "sha256": fp["sha256"], "byte_length": fp["byte_length"]}
        )

    files_by_ref = {f["ref"]: f for f in files_out}

    for segment in segments:
        association = associations_by_tid[segment.transcription_id]
        source_ref = f"source/{segment.source_fixture_name}"
        t0_run_ref = f"t0/{segment.transcription_id}/run.json"
        head_ref_candidate = f"t0/{segment.transcription_id}/head.json"
        t0_head_ref = head_ref_candidate if head_ref_candidate in files_by_ref else None
        raw_prefix = f"t0/{segment.transcription_id}/raw/"
        t0_raw_refs = sorted(ref for ref in files_by_ref if ref.startswith(raw_prefix))
        if not t0_raw_refs:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_t0_raw",
                segment.transcription_id,
            )
        params = require_processing_fields(
            processing_params(
                association,
                staging_dir / "t0" / segment.transcription_id / "run.json",
            ),
            transcription_id=segment.transcription_id,
        )
        if source_ref not in files_by_ref:
            raise DossierT0FixtureError("dossier_t0_fixture_missing_copied_source", source_ref)
        if files_by_ref[source_ref]["sha256"] != segment.source_sha256.lower():
            raise DossierT0FixtureError(
                "dossier_t0_fixture_source_hash_mismatch",
                source_ref,
            )
        segments_out.append(
            {
                "position": segment.position,
                "transcription_id": segment.transcription_id,
                "source_ref": source_ref,
                "source_sha256": segment.source_sha256.lower(),
                "t0_run_ref": t0_run_ref,
                "t0_head_ref": t0_head_ref,
                "t0_raw_refs": t0_raw_refs,
                "model": params["model"],
                "extraction_mode": params["extraction_mode"],
                "redundancy_count": params["redundancy_count"],
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "dossier_id": dossier_id,
        "segments": segments_out,
        "files": sorted(files_out, key=lambda f: f["ref"]),
    }


def validate_fixture_dir(
    fixture_dir: Path,
    *,
    expected_plan: Any | None = None,
) -> dict[str, Any]:
    root = Path(fixture_dir)
    if not root.is_dir():
        raise DossierT0FixtureError("dossier_t0_fixture_missing_packet", str(root))
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        raise DossierT0FixtureError("dossier_t0_fixture_missing_manifest", str(manifest_path))
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_manifest",
            str(exc),
        ) from exc
    if not isinstance(manifest, dict):
        raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "root must be object")

    unexpected = set(manifest.keys()) - _MANIFEST_KEYS
    if unexpected:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_unexpected_manifest_field",
            ",".join(sorted(unexpected)),
        )
    if set(manifest.keys()) != _MANIFEST_KEYS:
        missing = _MANIFEST_KEYS - set(manifest.keys())
        raise DossierT0FixtureError(
            "dossier_t0_fixture_malformed_manifest",
            f"missing fields: {','.join(sorted(missing))}",
        )

    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_schema_mismatch",
            str(manifest.get("schema_version")),
        )

    fixture_id = require_nonblank_str(
        manifest.get("fixture_id"),
        reason="dossier_t0_fixture_malformed_manifest",
        detail="fixture_id",
    )
    dossier_id = require_nonblank_str(
        manifest.get("dossier_id"),
        reason="dossier_t0_fixture_malformed_manifest",
        detail="dossier_id",
    )
    segments = manifest.get("segments")
    files = manifest.get("files")
    if not isinstance(segments, list) or not segments:
        raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "segments")
    if not isinstance(files, list) or not files:
        raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "files")

    positions: set[int] = set()
    transcription_ids: set[str] = set()
    declared_refs: set[str] = set()
    prior_position = 0

    def _declare(ref: str) -> None:
        if ref in declared_refs:
            raise DossierT0FixtureError("dossier_t0_fixture_duplicate_ref", ref)
        declared_refs.add(ref)

    for segment in segments:
        if not isinstance(segment, dict):
            raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "segment")
        unexpected_seg = set(segment.keys()) - _SEGMENT_KEYS
        if unexpected_seg:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_unexpected_segment_field",
                ",".join(sorted(unexpected_seg)),
            )
        if set(segment.keys()) != _SEGMENT_KEYS:
            missing = _SEGMENT_KEYS - set(segment.keys())
            raise DossierT0FixtureError(
                "dossier_t0_fixture_malformed_manifest",
                f"segment missing fields: {','.join(sorted(missing))}",
            )

        position = require_strict_int(
            segment.get("position"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail="position",
            positive=True,
        )
        if position <= prior_position:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_invalid_segment_order",
                f"positions must ascend; saw {prior_position} then {position}",
            )
        prior_position = position
        if position in positions:
            raise DossierT0FixtureError("dossier_t0_fixture_duplicate_position", str(position))
        positions.add(position)

        tid = require_nonblank_str(
            segment.get("transcription_id"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail="transcription_id",
        )
        if "/" in tid or "\\" in tid or tid in {".", ".."}:
            raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "transcription_id")
        if tid in transcription_ids:
            raise DossierT0FixtureError("dossier_t0_fixture_duplicate_transcription_id", tid)
        transcription_ids.add(tid)

        source_ref = assert_safe_ref(segment.get("source_ref"))
        source_name = Path(source_ref).name
        if source_ref != f"source/{source_name}" or "/" in source_name:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_invalid_source_ref",
                source_ref,
            )
        _declare(source_ref)

        t0_run_ref = assert_safe_ref(segment.get("t0_run_ref"))
        if t0_run_ref != f"t0/{tid}/run.json":
            raise DossierT0FixtureError("dossier_t0_fixture_invalid_t0_run_ref", t0_run_ref)
        _declare(t0_run_ref)

        head_ref = segment.get("t0_head_ref")
        if head_ref is not None:
            head_ref_s = assert_safe_ref(head_ref)
            if head_ref_s != f"t0/{tid}/head.json":
                raise DossierT0FixtureError("dossier_t0_fixture_invalid_t0_head_ref", head_ref_s)
            _declare(head_ref_s)

        raw_refs = segment.get("t0_raw_refs")
        if not isinstance(raw_refs, list):
            raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "t0_raw_refs")
        if not raw_refs:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_missing_t0_raw",
                tid,
            )
        raw_prefix = f"t0/{tid}/raw/"
        for ref in raw_refs:
            ref_s = assert_safe_ref(ref)
            if not ref_s.startswith(raw_prefix):
                raise DossierT0FixtureError("dossier_t0_fixture_invalid_t0_raw_ref", ref_s)
            remainder = ref_s[len(raw_prefix) :]
            if not remainder or "/" in remainder or not remainder.endswith(".json"):
                raise DossierT0FixtureError("dossier_t0_fixture_invalid_t0_raw_ref", ref_s)
            _declare(ref_s)

        require_hex_sha256(
            segment.get("source_sha256"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail="source_sha256",
        )

        require_nonblank_str(
            segment.get("model"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail="model",
        )
        require_nonblank_str(
            segment.get("extraction_mode"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail="extraction_mode",
        )
        require_strict_int(
            segment.get("redundancy_count"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail="redundancy_count",
            positive=True,
        )

    file_refs: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise DossierT0FixtureError("dossier_t0_fixture_malformed_manifest", "file entry")
        unexpected_file = set(entry.keys()) - _FILE_KEYS
        if unexpected_file:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_unexpected_file_field",
                ",".join(sorted(unexpected_file)),
            )
        if set(entry.keys()) != _FILE_KEYS:
            missing = _FILE_KEYS - set(entry.keys())
            raise DossierT0FixtureError(
                "dossier_t0_fixture_malformed_manifest",
                f"file missing fields: {','.join(sorted(missing))}",
            )
        ref_s = assert_safe_ref(entry.get("ref"))
        if ref_s in file_refs:
            raise DossierT0FixtureError("dossier_t0_fixture_duplicate_ref", ref_s)
        file_refs.add(ref_s)
        entry_sha = require_hex_sha256(
            entry.get("sha256"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail=f"files.sha256:{ref_s}",
        )
        byte_length = require_strict_int(
            entry.get("byte_length"),
            reason="dossier_t0_fixture_malformed_manifest",
            detail=f"byte_length:{ref_s}",
            positive=False,
        )
        path = root / Path(*ref_s.split("/"))
        if not path.is_file():
            raise DossierT0FixtureError("dossier_t0_fixture_missing_file", ref_s)
        fp = file_fingerprint(path)
        if fp["sha256"] != entry_sha:
            raise DossierT0FixtureError("dossier_t0_fixture_file_hash_mismatch", ref_s)
        if byte_length != fp["byte_length"]:
            raise DossierT0FixtureError("dossier_t0_fixture_file_size_mismatch", ref_s)

    if declared_refs != file_refs:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_ref_set_mismatch",
            f"declared={sorted(declared_refs)} files={sorted(file_refs)}",
        )

    sha_by_ref = {str(entry["ref"]): str(entry["sha256"]) for entry in files}
    for segment in segments:
        source_ref = str(segment["source_ref"])
        segment_sha = str(segment["source_sha256"])
        file_sha = sha_by_ref.get(source_ref)
        if file_sha != segment_sha:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_source_hash_mismatch",
                f"{source_ref}: segment={segment_sha} files={file_sha}",
            )

    on_disk_refs = _packet_file_refs(root)
    if on_disk_refs != file_refs:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_undeclared_files",
            f"on_disk={sorted(on_disk_refs)} files={sorted(file_refs)}",
        )

    assert_no_host_paths(manifest)
    _assert_allowlisted_topology(root, segments)

    if expected_plan is not None:
        if fixture_id != expected_plan.fixture_id:
            raise DossierT0FixtureError(CONFLICT_REASON, "fixture_id mismatch")
        if dossier_id != expected_plan.dossier_id:
            raise DossierT0FixtureError(CONFLICT_REASON, "dossier_id mismatch")
        if len(segments) != len(expected_plan.segments):
            raise DossierT0FixtureError(CONFLICT_REASON, "segment count mismatch")
        for planned, existing in zip(expected_plan.segments, segments, strict=True):
            if planned.position != existing.get("position"):
                raise DossierT0FixtureError(CONFLICT_REASON, "segment position mismatch")
            if planned.transcription_id != existing.get("transcription_id"):
                raise DossierT0FixtureError(CONFLICT_REASON, "transcription_id mismatch")
            if planned.source_sha256.lower() != str(existing.get("source_sha256") or "").lower():
                raise DossierT0FixtureError(CONFLICT_REASON, "source_sha256 mismatch")
            expected_source_ref = f"source/{planned.source_fixture_name}"
            if existing.get("source_ref") != expected_source_ref:
                raise DossierT0FixtureError(CONFLICT_REASON, "source_ref mismatch")

    return manifest


def build_set_manifest_payload(fixture_ids: Sequence[str]) -> dict[str, Any]:
    fixtures: list[dict[str, str]] = []
    seen: set[str] = set()
    for fixture_id in fixture_ids:
        fid = _require_safe_fixture_id(fixture_id)
        if fid in seen:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_duplicate_fixture_id",
                fid,
            )
        seen.add(fid)
        manifest_ref = f"{fid}/{MANIFEST_NAME}"
        assert_safe_ref(manifest_ref)
        fixtures.append({"fixture_id": fid, "manifest_ref": manifest_ref})
    return {
        "schema_version": SET_SCHEMA_VERSION,
        "fixtures": fixtures,
    }


def validate_set_manifest_payload(payload: Mapping[str, Any]) -> None:
    if not isinstance(payload, dict):
        raise DossierT0FixtureError("dossier_t0_fixture_malformed_set_manifest", "root")
    unexpected = set(payload.keys()) - _SET_MANIFEST_KEYS
    if unexpected:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_unexpected_set_manifest_field",
            ",".join(sorted(unexpected)),
        )
    if payload.get("schema_version") != SET_SCHEMA_VERSION:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_schema_mismatch",
            str(payload.get("schema_version")),
        )
    fixtures = payload.get("fixtures")
    if not isinstance(fixtures, list) or not fixtures:
        raise DossierT0FixtureError("dossier_t0_fixture_malformed_set_manifest", "fixtures")
    seen: set[str] = set()
    for item in fixtures:
        if not isinstance(item, dict):
            raise DossierT0FixtureError("dossier_t0_fixture_malformed_set_manifest", "member")
        unexpected_member = set(item.keys()) - _SET_MEMBER_KEYS
        if unexpected_member:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_unexpected_set_manifest_field",
                ",".join(sorted(unexpected_member)),
            )
        fid = _require_safe_fixture_id(item.get("fixture_id"))
        if fid in seen:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_duplicate_fixture_id",
                fid,
            )
        seen.add(fid)
        manifest_ref = assert_safe_ref(item.get("manifest_ref"))
        expected_ref = f"{fid}/{MANIFEST_NAME}"
        if manifest_ref != expected_ref:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_set_member_ref_mismatch",
                f"expected {expected_ref}, got {manifest_ref}",
            )


def _require_safe_fixture_id(value: Any) -> str:
    fid = require_nonblank_str(
        value,
        reason="dossier_t0_fixture_invalid_plan",
        detail="fixture_id",
    )
    if Path(fid).is_absolute() or fid.startswith("/") or fid.startswith("\\"):
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_plan",
            f"fixture_id must be a single path segment, got {fid!r}",
        )
    if len(fid) >= 2 and fid[1] == ":":
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_plan",
            f"fixture_id must be a single path segment, got {fid!r}",
        )
    if "/" in fid or "\\" in fid or ".." in fid or fid in {".", ".."}:
        raise DossierT0FixtureError(
            "dossier_t0_fixture_invalid_plan",
            f"fixture_id must be a single path segment, got {fid!r}",
        )
    return fid


def _packet_file_refs(root: Path) -> set[str]:
    refs: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel == MANIFEST_NAME:
            continue
        refs.add(rel)
    return refs


def _assert_allowlisted_topology(root: Path, segments: Sequence[Mapping[str, Any]]) -> None:
    allowed_dirs = {"source", "t0"}
    for child in root.iterdir():
        if child.name == MANIFEST_NAME and child.is_file():
            continue
        if child.name not in allowed_dirs:
            raise DossierT0FixtureError(
                "dossier_t0_fixture_allowlist_violation",
                child.name,
            )

    source_dir = root / "source"
    if source_dir.exists() and not source_dir.is_dir():
        raise DossierT0FixtureError("dossier_t0_fixture_allowlist_violation", "source")
    if source_dir.is_dir():
        for path in source_dir.rglob("*"):
            if path.is_dir():
                raise DossierT0FixtureError(
                    "dossier_t0_fixture_allowlist_violation",
                    path.relative_to(root).as_posix(),
                )
            rel = path.relative_to(root).as_posix()
            if rel.count("/") != 1:
                raise DossierT0FixtureError("dossier_t0_fixture_allowlist_violation", rel)

    t0_dir = root / "t0"
    expected_tids = {str(s["transcription_id"]) for s in segments}
    if t0_dir.exists() and not t0_dir.is_dir():
        raise DossierT0FixtureError("dossier_t0_fixture_allowlist_violation", "t0")
    if t0_dir.is_dir():
        for child in t0_dir.iterdir():
            if not child.is_dir() or child.name not in expected_tids:
                raise DossierT0FixtureError(
                    "dossier_t0_fixture_allowlist_violation",
                    child.relative_to(root).as_posix(),
                )
            for path in child.rglob("*"):
                rel = path.relative_to(root).as_posix()
                parts = rel.split("/")
                if path.is_dir():
                    if parts != ["t0", child.name, "raw"]:
                        raise DossierT0FixtureError(
                            "dossier_t0_fixture_allowlist_violation",
                            rel,
                        )
                    continue
                if parts == ["t0", child.name, "run.json"]:
                    continue
                if parts == ["t0", child.name, "head.json"]:
                    continue
                if (
                    len(parts) == 4
                    and parts[0] == "t0"
                    and parts[1] == child.name
                    and parts[2] == "raw"
                    and parts[3].endswith(".json")
                ):
                    continue
                raise DossierT0FixtureError("dossier_t0_fixture_allowlist_violation", rel)

    for banned_name in ("consensus", "alignment", "final", "transcript_edit"):
        for hit in root.rglob(banned_name):
            raise DossierT0FixtureError(
                "dossier_t0_fixture_allowlist_violation",
                hit.relative_to(root).as_posix(),
            )
