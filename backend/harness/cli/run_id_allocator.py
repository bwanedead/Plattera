"""Automatic CLI run-id allocation (control-plane only)."""

from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

from .run_layout import (
    BY_LOOP_KIND_DIRNAME,
    RunLayoutError,
    allocate_run_directory,
    by_loop_kind_root,
    find_run_directory_candidates,
    normalize_run_collection,
    normalize_run_id,
)

_SEQUENCE_DIRNAME = ".run_id_sequences"
_LOCK_FILENAME = "allocate.lock"
_COUNTER_FILENAME = "counter.json"
_RUN_ID_SUFFIX_PATTERN = re.compile(r"-live-r(\d{8})$")
_LOCK_WAIT_SECONDS = 30.0
_IN_PROCESS_ALLOCATOR_LOCK = threading.Lock()


class RunIdAllocatorError(RunLayoutError):
    """Raised when automatic run-id allocation fails."""


@dataclass(frozen=True)
class AllocatedCliRunId:
    run_id: str
    run_collection: str
    run_dir: Path
    human_timeline_path: Path


def collection_to_run_id_prefix(run_collection: str) -> str:
    collection = normalize_run_collection(run_collection)
    return collection.replace("_", "-")


def allocate_automatic_run_id(*, run_collection: str) -> AllocatedCliRunId:
    """Allocate the next monotonic run id for a collection under a cross-process lock."""
    collection = normalize_run_collection(run_collection)
    prefix = collection_to_run_id_prefix(collection)
    sequence_root = _sequence_root(collection)
    sequence_root.mkdir(parents=True, exist_ok=True)
    lock_path = sequence_root / _LOCK_FILENAME
    counter_path = sequence_root / _COUNTER_FILENAME

    with _cross_process_lock(lock_path):
        counter = _read_counter(counter_path)
        for _attempt in range(1000):
            counter += 1
            run_id = f"{prefix}-live-r{counter:08d}"
            normalize_run_id(run_id)
            if find_run_directory_candidates(run_id):
                continue
            run_dir = allocate_run_directory(run_id=run_id, run_collection=collection)
            _write_counter_atomic(counter_path, counter)
            timeline = run_dir / "audit" / "human" / "timeline.md"
            return AllocatedCliRunId(
                run_id=run_id,
                run_collection=collection,
                run_dir=run_dir,
                human_timeline_path=timeline,
            )
    raise RunIdAllocatorError("run_id_allocation_exhausted")


def _sequence_root(run_collection: str) -> Path:
    return by_loop_kind_root() / normalize_run_collection(run_collection) / _SEQUENCE_DIRNAME


def _read_counter(counter_path: Path) -> int:
    if not counter_path.is_file():
        return _recover_counter_from_existing_runs(counter_path.parent.parent)
    try:
        data = json.loads(counter_path.read_text(encoding="utf-8"))
        return max(0, int(data.get("next") or 0))
    except Exception:
        return _recover_counter_from_existing_runs(counter_path.parent.parent)


def _recover_counter_from_existing_runs(collection_dir: Path) -> int:
    prefix = collection_to_run_id_prefix(collection_dir.name)
    pattern = re.compile(rf"^{re.escape(prefix)}-live-r(\d{{8}})$")
    highest = 0
    if not collection_dir.is_dir():
        return 0
    for child in collection_dir.iterdir():
        if not child.is_dir():
            continue
        match = pattern.fullmatch(child.name)
        if match:
            highest = max(highest, int(match.group(1)))
    return highest


def _write_counter_atomic(counter_path: Path, counter: int) -> None:
    payload = {
        "next": counter,
        "updated_at_epoch_seconds": time.time(),
        "schema_version": "cli_run_id_counter.v1",
    }
    tmp = counter_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(counter_path)


def _acquire_os_file_lock(fd: int) -> None:
    """Acquire a non-blocking exclusive lock on the open lock file descriptor."""
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError from exc
        return
    import errno
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            raise BlockingIOError from exc
        raise


def _release_os_file_lock(fd: int) -> None:
    if sys.platform == "win32":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(fd, fcntl.LOCK_UN)


class _cross_process_lock:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._fd: int | None = None
        self._lock_token: str | None = None
        self._in_process_acquired = False

    def __enter__(self) -> _cross_process_lock:
        _IN_PROCESS_ALLOCATOR_LOCK.acquire()
        self._in_process_acquired = True
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            deadline = time.time() + _LOCK_WAIT_SECONDS
            while True:
                fd: int | None = None
                try:
                    fd = os.open(str(self._path), os.O_CREAT | os.O_RDWR)
                    _acquire_os_file_lock(fd)
                    self._fd = fd
                    self._lock_token = f"{os.getpid()}:{uuid.uuid4().hex}"
                    os.ftruncate(self._fd, 0)
                    os.lseek(self._fd, 0, os.SEEK_SET)
                    os.write(self._fd, self._lock_token.encode("ascii"))
                    return self
                except BlockingIOError:
                    if fd is not None:
                        os.close(fd)
                    if time.time() >= deadline:
                        raise RunIdAllocatorError("run_id_allocation_lock_timeout")
                    time.sleep(0.05)
                except Exception:
                    if fd is not None:
                        try:
                            os.close(fd)
                        except Exception:
                            pass
                    raise
        except Exception:
            if self._in_process_acquired:
                _IN_PROCESS_ALLOCATOR_LOCK.release()
                self._in_process_acquired = False
            raise

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if self._fd is not None:
                try:
                    _release_os_file_lock(self._fd)
                except Exception:
                    pass
                try:
                    os.close(self._fd)
                except Exception:
                    pass
                self._fd = None
        finally:
            if self._in_process_acquired:
                _IN_PROCESS_ALLOCATOR_LOCK.release()
                self._in_process_acquired = False
