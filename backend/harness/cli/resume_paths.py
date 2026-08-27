"""Shared paths for harness CLI kernel resume checkpoints."""

from __future__ import annotations

from pathlib import Path

RESUME_CHECKPOINT_FILENAME = "kernel_resume.json"
TURN_CHECKPOINTS_DIRNAME = "resume_checkpoints"
TURN_CHECKPOINT_CANONICAL_SUFFIX = ".json.gz"
TURN_CHECKPOINT_LEGACY_SUFFIX = ".json"


def kernel_resume_path(run_dir: Path) -> Path:
    return run_dir / RESUME_CHECKPOINT_FILENAME


def _validated_turn(from_turn: int) -> int:
    turn = int(from_turn)
    if turn < 1:
        raise ValueError("from_turn_must_be_positive")
    return turn


def turn_checkpoint_canonical_path(*, run_dir: Path, from_turn: int) -> Path:
    """Canonical historical checkpoint: ``resume_checkpoints/turn_NNNN.json.gz``."""
    turn = _validated_turn(from_turn)
    return (
        run_dir
        / TURN_CHECKPOINTS_DIRNAME
        / f"turn_{turn:04d}{TURN_CHECKPOINT_CANONICAL_SUFFIX}"
    )


def turn_checkpoint_legacy_path(*, run_dir: Path, from_turn: int) -> Path:
    """Legacy historical checkpoint: ``resume_checkpoints/turn_NNNN.json`` (read-only)."""
    turn = _validated_turn(from_turn)
    return (
        run_dir
        / TURN_CHECKPOINTS_DIRNAME
        / f"turn_{turn:04d}{TURN_CHECKPOINT_LEGACY_SUFFIX}"
    )


def resolve_existing_turn_checkpoint(*, run_dir: Path, from_turn: int) -> Path | None:
    """Return the checkpoint path to load, canonical-first.

    If the canonical ``.json.gz`` file exists, it is selected even when corrupt —
    callers must refuse honestly and must not fall back to legacy JSON.
    """
    canonical = turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=from_turn)
    if canonical.is_file():
        return canonical
    legacy = turn_checkpoint_legacy_path(run_dir=run_dir, from_turn=from_turn)
    if legacy.is_file():
        return legacy
    return None


def turn_checkpoint_path_for_next_iteration(*, run_dir: Path, next_iteration: int) -> Path:
    """Map snapshot ``next_iteration`` to the canonical completed-turn checkpoint path."""
    n = int(next_iteration)
    if n < 2:
        raise ValueError("next_iteration_must_be_at_least_2_for_turn_checkpoint")
    return turn_checkpoint_canonical_path(run_dir=run_dir, from_turn=n - 1)
