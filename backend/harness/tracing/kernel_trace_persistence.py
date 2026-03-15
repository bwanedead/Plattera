"""Shared kernel-direct trace persistence utility (Phase 12 D2).

Provides a single best-effort helper used by all orchestration-kernel mode adapters
(deed-to-IR, transcript-edit) to persist a CanonicalTraceRecord built from live
KernelTraceCollector events and return its file-path ref.

Rules:
- Never raises — any I/O failure returns None so callers can proceed unblocked.
- Persists atomically (tmp-file + os.replace) next to the run artifact, or under
  the agent_kernel artifacts root as a fallback.
- File name convention: ``<run_id>_trace.json`` alongside the run artifact.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .service import build_kernel_direct_canonical_trace

if TYPE_CHECKING:
    from harness.orchestration_kernel.contracts import KernelLoopResult


def persist_kernel_trace(
    *,
    kernel_result: "KernelLoopResult",
    request_id_prefix: str,
) -> str | None:
    """Build and atomically persist a kernel-direct canonical trace artifact.

    Parameters
    ----------
    kernel_result:
        The ``KernelLoopResult`` returned by ``run_orchestration_kernel_loop()``.
        ``kernel_result.trace_events`` must be non-empty for anything to be written.
    request_id_prefix:
        Used as the fallback sub-directory name when the run artifact's parent
        directory cannot be determined.

    Returns
    -------
    str | None
        Absolute path to the persisted trace JSON, or ``None`` on any failure.
    """
    if not kernel_result.trace_events:
        return None
    try:
        run_artifact_ref = kernel_result.run_artifact_ref
        run_artifact = _load_run_artifact(run_artifact_ref)

        trace_record = build_kernel_direct_canonical_trace(
            trace_events=kernel_result.trace_events,
            run_artifact=run_artifact,
            run_artifact_ref=run_artifact_ref,
        )

        trace_dir = _resolve_trace_dir(
            run_artifact_ref=run_artifact_ref,
            request_id_prefix=request_id_prefix,
        )
        trace_dir.mkdir(parents=True, exist_ok=True)

        run_id = trace_record.run_id or "unknown_run"
        trace_path = trace_dir / f"{run_id}_trace.json"

        _atomic_write(path=trace_path, data=trace_record.model_dump(mode="json"))
        return str(trace_path)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_run_artifact(run_artifact_ref: str | None) -> dict[str, Any]:
    if not run_artifact_ref:
        return {}
    try:
        with open(run_artifact_ref, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _resolve_trace_dir(*, run_artifact_ref: str | None, request_id_prefix: str) -> Path:
    if run_artifact_ref:
        candidate = Path(run_artifact_ref).parent
        if candidate.exists():
            return candidate
    try:
        from config.paths import agent_kernel_artifacts_root
    except ModuleNotFoundError:
        from backend.config.paths import agent_kernel_artifacts_root  # type: ignore[no-redef]
    return agent_kernel_artifacts_root() / str(request_id_prefix)


def _atomic_write(*, path: Path, data: dict[str, Any]) -> None:
    fd, tmp = tempfile.mkstemp(prefix="kernel_trace_", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        try:
            os.replace(tmp, str(path))
        except PermissionError:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=2)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass
