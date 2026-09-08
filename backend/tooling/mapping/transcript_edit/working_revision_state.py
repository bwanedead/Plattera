"""Strict working-revision storage state reader.

Distinguishes empty, coherent head, manifest lag, recoverable orphan, and invalid
state. Never coerces malformed coordinates into allocation inputs. Present-but-
corrupt pointer/manifest/revision files are invalid — never treated as absent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from tooling.mapping.transcript_edit.paths import (
    transcript_edit_latest_pointer_path,
    transcript_edit_revision_path,
    transcript_edit_working_dir,
)
from tooling.mapping.transcript_edit.working_revision_atomic_io import (
    compact_dumps,
    content_sha256_of_doc,
)
from tooling.mapping.transcript_edit.working_revision_io import (
    ManifestStorageInvalid,
    load_json_file,
    load_or_init_manifest,
    parse_working_revision_ref,
    probe_json_object_file,
)

MAX_WORKING_REVISION = 9999

_REV_FILE_RE = re.compile(r"^rev_(\d{4})\.json$")

WorkingStorageKind = Literal[
    "empty",
    "coherent",
    "manifest_lag",
    "recoverable_orphan",
    "invalid",
]


@dataclass(frozen=True)
class WorkingStorageView:
    """Strict view of working-revision storage for allocate / recover / refuse."""

    kind: WorkingStorageKind
    head_revision: int | None
    head_ref_id: str | None
    file_max: int
    storage_max: int
    manifest_revision: int
    detail: str = ""


def _invalid(
    *,
    detail: str,
    file_max: int = 0,
    storage_max: int = 0,
    manifest_revision: int = 0,
    head_revision: int | None = None,
    head_ref_id: str | None = None,
) -> WorkingStorageView:
    return WorkingStorageView(
        kind="invalid",
        head_revision=head_revision,
        head_ref_id=head_ref_id,
        file_max=file_max,
        storage_max=storage_max,
        manifest_revision=manifest_revision,
        detail=detail,
    )


def strict_revision_int(value: Any, *, allow_zero: bool = False) -> int | None:
    """Return a valid revision int, or None when the value is malformed."""
    if type(value) is not int or isinstance(value, bool):
        return None
    lo = 0 if allow_zero else 1
    if value < lo or value > MAX_WORKING_REVISION:
        return None
    return value


def revision_coordinate_error(
    revision_doc: dict[str, Any],
    *,
    expected_revision: int | None = None,
) -> str | None:
    """Return an error detail when revision/ref/path coordinates disagree."""
    rev = strict_revision_int(revision_doc.get("revision"))
    if rev is None:
        return "revision must be an exact integer in 1..9999."
    if expected_revision is not None and rev != expected_revision:
        return f"revision {rev} does not match expected coordinate {expected_revision}."
    ref = revision_doc.get("ref_id")
    if type(ref) is not str or not ref.strip():
        return "ref_id must be a nonblank string."
    digits = parse_working_revision_ref(ref.strip())
    if digits is None:
        return "ref_id must match transcript_edit:working:rev:NNNN."
    if int(digits) != rev:
        return "ref_id revision digits do not match revision field."
    return None


def list_revision_file_numbers(work_dir: Path) -> set[int]:
    """Return the set of revision numbers present as ``rev_NNNN.json`` files."""
    found: set[int] = set()
    if not work_dir.is_dir():
        return found
    for entry in work_dir.iterdir():
        if not entry.is_file() or entry.is_symlink():
            continue
        m = _REV_FILE_RE.match(entry.name)
        if not m:
            continue
        n = int(m.group(1))
        if 1 <= n <= MAX_WORKING_REVISION:
            found.add(n)
    return found


def highest_revision_file_number(work_dir: Path) -> int:
    nums = list_revision_file_numbers(work_dir)
    return max(nums) if nums else 0


def _contiguous_prefix_error(present: set[int], *, through: int) -> str | None:
    """Require files 1..through all exist with no extras below through."""
    if through < 1:
        return None if not present else "Unexpected revision files with empty head."
    expected = set(range(1, through + 1))
    missing = sorted(expected - present)
    if missing:
        return f"Missing intermediate revision coordinates: {missing}."
    extras_below = sorted(n for n in present if n < through and n not in expected)
    if extras_below:
        return f"Unexpected revision coordinates below head: {extras_below}."
    return None


def _load_revision_object(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    revision: int,
) -> tuple[dict[str, Any] | None, str | None]:
    """Return (doc, error). Distinguishes absent vs present-invalid."""
    digits = f"{revision:04d}"
    path = transcript_edit_revision_path(
        dossier_id, transcription_id, workspace_id, digits
    )
    probe = probe_json_object_file(path)
    if probe.kind == "absent":
        return None, f"Revision file rev_{digits}.json is absent."
    if probe.kind == "invalid":
        return None, probe.detail or f"Revision file rev_{digits}.json is malformed."
    assert probe.value is not None
    return probe.value, None


def _latest_pointer_view(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> tuple[int | None, str | None, str | None]:
    """Return (revision, ref_id, error).

    ``error`` is set when latest is present-but-invalid or disagrees with its
    revision document (including content_sha256 / byte_length).
    """
    path = transcript_edit_latest_pointer_path(dossier_id, transcription_id, workspace_id)
    probe = probe_json_object_file(path)
    if probe.kind == "absent":
        return None, None, None
    if probe.kind == "invalid":
        return None, None, probe.detail or "latest.json is present but malformed."
    latest = probe.value
    assert latest is not None

    rev = strict_revision_int(latest.get("revision"))
    if rev is None:
        return None, None, "latest.json revision is malformed."
    ref = latest.get("ref_id")
    if type(ref) is not str or not ref.strip():
        return None, None, "latest.json ref_id is malformed."
    ref = ref.strip()
    digits = parse_working_revision_ref(ref)
    if digits is None or int(digits) != rev:
        return None, None, "latest.json ref_id does not match revision."
    rel = latest.get("relative_path")
    if type(rel) is not str or not rel.strip():
        return None, None, "latest.json relative_path is required."
    expected_rel = f"working/rev_{digits}.json"
    if rel.strip().replace("\\", "/") != expected_rel:
        return None, None, "latest.json relative_path does not match revision."

    doc, load_err = _load_revision_object(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        revision=rev,
    )
    if load_err is not None:
        return None, None, f"latest.json points at a bad revision file: {load_err}"
    assert doc is not None
    coord_err = revision_coordinate_error(doc, expected_revision=rev)
    if coord_err is not None:
        return None, None, f"latest head revision file is incoherent: {coord_err}"

    expected_hash = content_sha256_of_doc(doc)
    expected_bytes = len(compact_dumps(doc).encode("utf-8"))
    got_hash = latest.get("content_sha256")
    if type(got_hash) is not str or not got_hash.strip():
        return None, None, "latest.json content_sha256 is malformed."
    if got_hash.strip() != expected_hash:
        return None, None, "latest.json content_sha256 does not match revision document."
    got_len = latest.get("byte_length")
    if type(got_len) is not int or isinstance(got_len, bool) or got_len < 0:
        return None, None, "latest.json byte_length is malformed."
    if got_len != expected_bytes:
        return None, None, "latest.json byte_length does not match revision document."

    return rev, ref, None


def _classify_recoverable_orphan(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
    head_revision: int | None,
    head_ref_id: str | None,
    present: set[int],
    file_max: int,
    man_rev: int,
) -> WorkingStorageView:
    """Allow recovery only for exactly the next coordinate (head+1 or 0001)."""
    expected_next = 1 if head_revision is None else head_revision + 1
    if expected_next > MAX_WORKING_REVISION:
        return _invalid(
            detail="Recoverable orphan would exceed revision capacity.",
            file_max=file_max,
            storage_max=file_max,
            manifest_revision=man_rev,
            head_revision=head_revision,
            head_ref_id=head_ref_id,
        )

    if head_revision is None:
        if present != {1}:
            return _invalid(
                detail=(
                    "Empty-head recovery requires exactly rev_0001.json with no other "
                    f"revision files; found {sorted(present)}."
                ),
                file_max=file_max,
                storage_max=file_max,
                manifest_revision=man_rev,
            )
    else:
        prefix_err = _contiguous_prefix_error(present, through=head_revision)
        if prefix_err is not None:
            return _invalid(
                detail=prefix_err,
                file_max=file_max,
                storage_max=max(file_max, head_revision),
                manifest_revision=man_rev,
                head_revision=head_revision,
                head_ref_id=head_ref_id,
            )
        above = sorted(n for n in present if n > head_revision)
        if above != [expected_next]:
            return _invalid(
                detail=(
                    f"Recoverable orphan must be exactly rev_{expected_next:04d}.json; "
                    f"found above head: {above}."
                ),
                file_max=file_max,
                storage_max=max(file_max, head_revision),
                manifest_revision=man_rev,
                head_revision=head_revision,
                head_ref_id=head_ref_id,
            )

    orphan_doc, load_err = _load_revision_object(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
        revision=expected_next,
    )
    if load_err is not None:
        return _invalid(
            detail=f"Orphan revision is unreadable: {load_err}",
            file_max=file_max,
            storage_max=max(file_max, expected_next),
            manifest_revision=man_rev,
            head_revision=head_revision,
            head_ref_id=head_ref_id,
        )
    assert orphan_doc is not None
    coord_err = revision_coordinate_error(orphan_doc, expected_revision=expected_next)
    if coord_err is not None:
        return _invalid(
            detail=f"Orphan revision is incoherent: {coord_err}",
            file_max=file_max,
            storage_max=max(file_max, expected_next),
            manifest_revision=man_rev,
            head_revision=head_revision,
            head_ref_id=head_ref_id,
        )

    return WorkingStorageView(
        kind="recoverable_orphan",
        head_revision=head_revision,
        head_ref_id=head_ref_id,
        file_max=expected_next,
        storage_max=expected_next,
        manifest_revision=man_rev,
        detail=f"Recoverable orphan at rev_{expected_next:04d}.",
    )


def read_working_storage_state(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> WorkingStorageView:
    """Strict storage classification used before allocate / recover / heal."""
    work_dir = transcript_edit_working_dir(dossier_id, transcription_id, workspace_id)
    present = list_revision_file_numbers(work_dir)
    file_max = max(present) if present else 0

    try:
        manifest = load_or_init_manifest(dossier_id, transcription_id, workspace_id)
    except ManifestStorageInvalid as exc:
        return _invalid(
            detail=str(exc.detail),
            file_max=file_max,
            storage_max=file_max,
        )

    man_rev = strict_revision_int(manifest.get("latest_revision"), allow_zero=True)
    if man_rev is None:
        return _invalid(
            detail="manifest.latest_revision is malformed.",
            file_max=file_max,
            storage_max=file_max,
        )
    man_ref = manifest.get("latest_working_ref_id")
    if man_rev > 0:
        if type(man_ref) is not str or not man_ref.strip():
            return _invalid(
                detail="manifest.latest_working_ref_id is malformed.",
                file_max=file_max,
                storage_max=max(file_max, man_rev),
                manifest_revision=man_rev,
            )
        digits = parse_working_revision_ref(man_ref.strip())
        if digits is None or int(digits) != man_rev:
            return _invalid(
                detail="manifest latest_working_ref_id does not match latest_revision.",
                file_max=file_max,
                storage_max=max(file_max, man_rev),
                manifest_revision=man_rev,
            )

    latest_rev, latest_ref, latest_err = _latest_pointer_view(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        workspace_id=workspace_id,
    )
    if latest_err is not None:
        return _invalid(
            detail=latest_err,
            file_max=file_max,
            storage_max=max(file_max, man_rev),
            manifest_revision=man_rev,
        )

    if latest_rev is None and not present and man_rev == 0:
        return WorkingStorageView(
            kind="empty",
            head_revision=None,
            head_ref_id=None,
            file_max=0,
            storage_max=0,
            manifest_revision=0,
        )

    if latest_rev is None and not present and man_rev > 0:
        return _invalid(
            detail="manifest claims a head but latest.json is absent.",
            file_max=0,
            storage_max=man_rev,
            manifest_revision=man_rev,
        )

    if latest_rev is None and present:
        if man_rev > 0:
            return _invalid(
                detail="manifest claims a head but latest.json is absent.",
                file_max=file_max,
                storage_max=max(file_max, man_rev),
                manifest_revision=man_rev,
            )
        return _classify_recoverable_orphan(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            head_revision=None,
            head_ref_id=None,
            present=present,
            file_max=file_max,
            man_rev=man_rev,
        )

    assert latest_rev is not None and latest_ref is not None

    prefix_err = _contiguous_prefix_error(present, through=latest_rev)
    if prefix_err is not None:
        return _invalid(
            detail=prefix_err,
            file_max=file_max,
            storage_max=max(file_max, latest_rev, man_rev),
            manifest_revision=man_rev,
            head_revision=latest_rev,
            head_ref_id=latest_ref,
        )

    above = sorted(n for n in present if n > latest_rev)
    if above:
        return _classify_recoverable_orphan(
            dossier_id=dossier_id,
            transcription_id=transcription_id,
            workspace_id=workspace_id,
            head_revision=latest_rev,
            head_ref_id=latest_ref,
            present=present,
            file_max=file_max,
            man_rev=man_rev,
        )

    storage_max = max(latest_rev, man_rev)
    if man_rev > latest_rev:
        return _invalid(
            detail="manifest.latest_revision is ahead of latest.json.",
            file_max=file_max,
            storage_max=storage_max,
            manifest_revision=man_rev,
            head_revision=latest_rev,
            head_ref_id=latest_ref,
        )

    if man_rev < latest_rev:
        return WorkingStorageView(
            kind="manifest_lag",
            head_revision=latest_rev,
            head_ref_id=latest_ref,
            file_max=file_max,
            storage_max=storage_max,
            manifest_revision=man_rev,
            detail="manifest lags behind latest.json.",
        )

    return WorkingStorageView(
        kind="coherent",
        head_revision=latest_rev,
        head_ref_id=latest_ref,
        file_max=file_max,
        storage_max=storage_max,
        manifest_revision=man_rev,
    )
