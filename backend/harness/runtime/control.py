"""Generic run-control transport.

Host-authored control-file surface used by operators (and, in the future, the
app) to pause or stop a running harness loop gracefully at safe boundaries.
This module is purely mechanical: it defines the control request shape, the
atomic write/read/consume helpers, and nothing else. No orchestration
semantics, no domain logic, no process signaling.

File layout: ``<run_dir>/control.json``

Semantics are enforced by the orchestrator, not here:

* ``pause`` / ``stop``   graceful operator interruption, still resumable.
* Both are checked only at safe loop boundaries.
* Control file is host/operator-authored, never model-authored.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

_LOG = logging.getLogger(__name__)

CONTROL_FILENAME = "control.json"
CONTROL_SCHEMA_VERSION = 1
_ALLOWED_COMMANDS = frozenset({"pause", "stop"})


@dataclass(frozen=True)
class RunControlRequest:
    """A single operator control request persisted to ``control.json``."""

    schema_version: int
    request_id: str
    command: str
    requested_at_epoch_seconds: float
    reason: str | None = None
    requested_by: str = "cli"

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json_dict(cls, data: dict[str, Any]) -> "RunControlRequest":
        command = str(data.get("command") or "").strip().lower()
        if command not in _ALLOWED_COMMANDS:
            raise ValueError(f"invalid_control_command:{command or 'empty'}")
        try:
            schema_version = int(data.get("schema_version") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_control_schema_version") from exc
        if schema_version != CONTROL_SCHEMA_VERSION:
            raise ValueError(f"unsupported_control_schema_version:{schema_version}")
        request_id = str(data.get("request_id") or "").strip()
        if not request_id:
            raise ValueError("missing_control_request_id")
        try:
            requested_at = float(data.get("requested_at_epoch_seconds") or 0.0)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_control_requested_at") from exc
        reason_raw = data.get("reason")
        reason = str(reason_raw).strip() if isinstance(reason_raw, str) and reason_raw.strip() else None
        requested_by = str(data.get("requested_by") or "cli").strip() or "cli"
        return cls(
            schema_version=schema_version,
            request_id=request_id,
            command=command,
            requested_at_epoch_seconds=requested_at,
            reason=reason,
            requested_by=requested_by,
        )


def control_path(run_dir: str | Path) -> Path:
    """Return the canonical ``control.json`` path for a run directory."""
    return Path(run_dir) / CONTROL_FILENAME


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_control_", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def write_run_control_request(
    target: str | Path,
    *,
    command: str,
    reason: str | None = None,
    requested_by: str = "cli",
    request_id: str | None = None,
) -> RunControlRequest:
    """Persist a control request to ``target`` atomically."""
    cmd = str(command or "").strip().lower()
    if cmd not in _ALLOWED_COMMANDS:
        raise ValueError(f"invalid_control_command:{cmd or 'empty'}")
    req = RunControlRequest(
        schema_version=CONTROL_SCHEMA_VERSION,
        request_id=(str(request_id).strip() if request_id else uuid4().hex),
        command=cmd,
        requested_at_epoch_seconds=time(),
        reason=(str(reason).strip() if isinstance(reason, str) and reason.strip() else None),
        requested_by=str(requested_by or "cli").strip() or "cli",
    )
    _atomic_write_json(Path(target), req.to_json_dict())
    return req


def read_run_control_request(source: str | Path) -> RunControlRequest | None:
    """Read a control request if present and valid; return ``None`` otherwise.

    Invalid / corrupt control files are treated as absent rather than raising,
    so a malformed file cannot crash the loop at a safe boundary. Callers that
    need forensic detail can inspect the file directly.
    """
    path = Path(source)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _LOG.warning("run_control unreadable at %s", path, exc_info=True)
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return RunControlRequest.from_json_dict(raw)
    except ValueError:
        _LOG.warning("run_control invalid at %s", path, exc_info=True)
        return None


def consume_run_control_request(source: str | Path) -> bool:
    """Remove a control file if present. Returns True when a file was removed."""
    path = Path(source)
    try:
        path.unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError:
        _LOG.warning("run_control unlink failed at %s", path, exc_info=True)
        return False


def build_run_control_reader_for_path(
    path: str | Path,
):
    """Return a zero-arg callable that reads control requests from ``path``."""
    resolved = Path(path)

    def _read() -> RunControlRequest | None:
        return read_run_control_request(resolved)

    return _read
