"""Best-effort per-turn kernel resume checkpoint writes (mechanical persistence)."""

from __future__ import annotations

import logging

from ...execution.session import ExecutionSessionManager
from ..memory import LoopMemoryState
from ..memory.resume_snapshot import build_kernel_resume_snapshot
from .lifecycle import OrchestrationLifecycle

_LOG = logging.getLogger(__name__)


def write_resume_checkpoint(
    *,
    lifecycle: OrchestrationLifecycle,
    loop_memory: LoopMemoryState,
    session_manager: ExecutionSessionManager,
    session_id: str,
    iteration: int,
) -> None:
    """Best-effort per-turn ``kernel_resume.json`` snapshot; never raises."""
    writer = lifecycle.resume_checkpoint_writer
    if writer is None:
        return
    try:
        snap = build_kernel_resume_snapshot(
            loop_memory=loop_memory,
            session_manager=session_manager,
            session_id=session_id,
            next_iteration=iteration + 1,
        )
        writer(snap)
    except Exception:
        _LOG.warning("resume_checkpoint_write_failed", exc_info=True)
