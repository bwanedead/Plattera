"""Shared exclusive lock for competing transcript-edit working writers."""

from __future__ import annotations

import sys
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from tooling.mapping.transcript_edit.paths import (
    UnsafeArtifactPathSegmentError,
    transcript_edit_working_dir,
)


class WorkingWriteLockBusy(Exception):
    """Another writer holds the working-write lock."""


class WorkingWriteLockFailed(Exception):
    """Unable to acquire or prepare the working-write lock."""


@contextmanager
def working_write_lock(
    *,
    dossier_id: str,
    transcription_id: str,
    workspace_id: str,
) -> Iterator[None]:
    """Serialize save/copy/apply mutations for one transcription workspace."""
    try:
        work_dir = transcript_edit_working_dir(dossier_id, transcription_id, workspace_id)
        work_dir.mkdir(parents=True, exist_ok=True)
        lock_path = work_dir / ".write.lock"
        handle = open(lock_path, "a+b")
    except UnsafeArtifactPathSegmentError:
        raise
    except OSError as exc:
        raise WorkingWriteLockFailed(str(exc)) from exc

    locked = False
    try:
        try:
            if sys.platform == "win32":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
        except OSError as exc:
            raise WorkingWriteLockBusy() from exc
        yield
    finally:
        if locked:
            try:
                if sys.platform == "win32":
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass
        try:
            handle.close()
        except OSError:
            pass
