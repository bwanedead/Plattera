"""Shared harness memory: continuity, observability telemetry, and loop-local state.

Mission meaning and pack-specific interpretation live in ``mission_state`` and
outside the harness; this package holds generic per-run carriage only, not a
parallel work ontology.
"""

from .continuity import OrchestrationContinuity
from .loop_state import LoopMemoryState
from .resume_snapshot import (
    KERNEL_RESUME_SNAPSHOT_VERSION,
    build_kernel_resume_snapshot,
    hydrate_session_manager_from_resume_payload,
    merge_launch_latest_refs_with_resume_continuity,
    parse_kernel_resume_snapshot,
)
from .resume_snapshot_storage import load_kernel_resume_snapshot_from_path
from .telemetry import PromptContactTelemetry

__all__ = [
    "KERNEL_RESUME_SNAPSHOT_VERSION",
    "LoopMemoryState",
    "OrchestrationContinuity",
    "PromptContactTelemetry",
    "build_kernel_resume_snapshot",
    "hydrate_session_manager_from_resume_payload",
    "load_kernel_resume_snapshot_from_path",
    "merge_launch_latest_refs_with_resume_continuity",
    "parse_kernel_resume_snapshot",
]
