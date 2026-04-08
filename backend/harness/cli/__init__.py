"""Harness CLI: mission payload shaping and operator entrypoints (``python -m harness.cli.*``)."""

from .payload import build_mission_cli_payload

__all__ = [
    "build_mission_cli_payload",
]
