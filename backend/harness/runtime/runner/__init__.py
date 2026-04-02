"""Mechanical runtime runner package.

This package owns process lifecycle and CLI artifact writing only.
Do not add domain doctrine, mission-state authorship, closure policy, or
pack-specific semantics here.
"""

from __future__ import annotations

from .contracts import RuntimeAdapter, RuntimeArtifactTargets, RuntimeRunResult
from .runner import RuntimeRunner, RuntimeRunnerError, run_runtime_from_env

__all__ = [
    "RuntimeAdapter",
    "RuntimeArtifactTargets",
    "RuntimeRunResult",
    "RuntimeRunner",
    "RuntimeRunnerError",
    "run_runtime_from_env",
]
