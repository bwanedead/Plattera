from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any

from agent_kernel.models import KernelStepRequest
from agent_kernel.session import KernelSessionManager


def emit_progress(progress_cb: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if progress_cb is None:
        return
    try:
        progress_cb(payload)
    except Exception:
        return


def step_kernel_action(
    *,
    session_manager: KernelSessionManager,
    session_id: str,
    prefix: str,
    iteration: int,
    action_type: str,
    inputs: dict[str, Any],
):
    return session_manager.step(
        KernelStepRequest(
            session_id=session_id,
            idempotency_key=idempotency_key(prefix, iteration, inputs),
            action_type=action_type,
            inputs=inputs,
        )
    )


def normalized_mode(raw: str | None, allowed_modes: set[str], default_mode: str) -> str:
    value = (raw or "").strip().lower()
    if value in allowed_modes:
        return value
    return default_mode


def idempotency_key(prefix: str, iteration: int, inputs: dict[str, Any]) -> str:
    canonical = json.dumps(inputs, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{iteration:02d}-{digest}"


def read_step_outputs_inline(step_record: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(step_record, dict):
        return {}
    outputs_inline = step_record.get("outputs_inline")
    if isinstance(outputs_inline, dict):
        return outputs_inline
    return {}


def read_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def read_str_from_latest_refs(latest_refs: dict[str, Any], key: str) -> str | None:
    if not isinstance(latest_refs, dict):
        return None
    value = latest_refs.get(key)
    if isinstance(value, dict):
        path = value.get("artifact_path")
        return read_str(path)
    return read_str(value)
