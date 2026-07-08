"""Human-editable run control sidecar for CLI-hosted harness runs."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from time import time
from typing import Any
from uuid import uuid4

from .control import (
    CONTROL_SCHEMA_VERSION,
    RunControlRequest,
    read_run_control_request,
)

_LOG = logging.getLogger(__name__)

RUN_CONTROL_FILENAME = "run_control.json"
EMERGENCY_STOP_TRIGGERED_FILENAME = "emergency_stop_triggered.json"

DEFAULT_RUN_CONTROL_STATE: dict[str, Any] = {
    "emergency_stop": False,
    "stop": False,
    "pause": False,
    "message": None,
}


def run_control_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / RUN_CONTROL_FILENAME


def write_initial_run_control_sidecar(run_dir: str | Path) -> Path:
    """Create ``run_control.json`` with default operator controls if absent."""
    path = run_control_path(run_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(
            json.dumps(DEFAULT_RUN_CONTROL_STATE, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    return path


def read_run_control_sidecar(source: str | Path) -> tuple[dict[str, Any] | None, str | None]:
    """Return parsed sidecar state and optional parse error code."""
    path = Path(source)
    if not path.is_file():
        return None, None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        _LOG.warning("run_control_sidecar unreadable at %s", path, exc_info=True)
        return None, "run_control_sidecar_unreadable"
    if not isinstance(raw, dict):
        return None, "run_control_sidecar_invalid"
    return raw, None


def summarize_run_control_sidecar(source: str | Path) -> dict[str, Any]:
    """Return operator-facing sidecar summary for status/start output."""
    path = run_control_path(source) if not str(source).endswith(RUN_CONTROL_FILENAME) else Path(source)
    state, parse_err = read_run_control_sidecar(path)
    summary: dict[str, Any] = {
        "run_control_file": str(path.resolve()),
    }
    if parse_err:
        summary["parse_error"] = parse_err
        return summary
    if state is None:
        summary["present"] = False
        return summary
    summary["present"] = True
    summary["emergency_stop"] = bool(state.get("emergency_stop"))
    summary["stop"] = bool(state.get("stop"))
    summary["pause"] = bool(state.get("pause"))
    message = state.get("message")
    if isinstance(message, str) and message.strip():
        summary["message"] = message.strip()
    return summary


def emergency_stop_requested(source: str | Path) -> bool:
    state, parse_err = read_run_control_sidecar(source)
    if parse_err or state is None:
        return False
    return bool(state.get("emergency_stop"))


def build_sidecar_aware_run_control_reader(
    *,
    cli_command_path: str | Path,
    sidecar_path: str | Path,
):
    """Return a reader honoring ``control.json`` then cooperative ``run_control.json`` flags."""
    command_path = Path(cli_command_path)
    sidecar = Path(sidecar_path)
    last_honored: dict[str, tuple[str, float] | None] = {"value": None}

    def _read() -> RunControlRequest | None:
        cli_req = read_run_control_request(command_path)
        if cli_req is not None:
            return cli_req

        state, parse_err = read_run_control_sidecar(sidecar)
        if parse_err or state is None:
            return None

        try:
            mtime = float(sidecar.stat().st_mtime)
        except OSError:
            mtime = 0.0

        message_raw = state.get("message")
        reason = str(message_raw).strip() if isinstance(message_raw, str) and message_raw.strip() else None

        if bool(state.get("stop")):
            key = ("stop", mtime)
            if last_honored["value"] == key:
                return None
            last_honored["value"] = key
            return RunControlRequest(
                schema_version=CONTROL_SCHEMA_VERSION,
                request_id=f"sidecar-stop-{uuid4().hex[:12]}",
                command="stop",
                requested_at_epoch_seconds=time(),
                reason=reason,
                requested_by="run_control_sidecar",
            )

        if bool(state.get("pause")):
            key = ("pause", mtime)
            if last_honored["value"] == key:
                return None
            last_honored["value"] = key
            return RunControlRequest(
                schema_version=CONTROL_SCHEMA_VERSION,
                request_id=f"sidecar-pause-{uuid4().hex[:12]}",
                command="pause",
                requested_at_epoch_seconds=time(),
                reason=reason,
                requested_by="run_control_sidecar",
            )

        return None

    return _read
