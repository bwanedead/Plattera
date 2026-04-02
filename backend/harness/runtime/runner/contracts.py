"""Mechanical contracts for the generic runtime runner.

This surface is deliberately blind to domain meaning. Keep it limited to
adapter loading, opaque launch context transport, turn-surface composition, and
artifact payloads.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, runtime_checkable

from ..composition import TurnSurface


@dataclass(frozen=True)
class RuntimeArtifactTargets:
    done_file: Path
    result_file: Path

    @classmethod
    def from_env(
        cls,
        *,
        done_file_env: str = "HARNESS_CLI_DONE_FILE",
        result_file_env: str = "HARNESS_CLI_RESULT_FILE",
    ) -> RuntimeArtifactTargets:
        from os import environ

        done_file = _required_env_path(done_file_env, environ)
        result_file = _required_env_path(result_file_env, environ)
        return cls(done_file=done_file, result_file=result_file)


@dataclass(frozen=True)
class RuntimeRunResult:
    status: str
    reason_code: str | None = None
    result_payload: dict[str, Any] = field(default_factory=dict)
    done_payload: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class RuntimeAdapter(Protocol):
    def build_turn_surface(self, launch_context: Mapping[str, Any]) -> TurnSurface: ...


def _required_env_path(name: str, environ: Mapping[str, str]) -> Path:
    raw = str(environ.get(name) or "").strip()
    if not raw:
        raise RuntimeError(f"missing_required_runner_env:{name}")
    return Path(raw)
