"""Shared paths for harness CLI kernel resume checkpoints."""

from __future__ import annotations

from pathlib import Path

RESUME_CHECKPOINT_FILENAME = "kernel_resume.json"
TURN_CHECKPOINTS_DIRNAME = "resume_checkpoints"


def kernel_resume_path(run_dir: Path) -> Path:
    return run_dir / RESUME_CHECKPOINT_FILENAME


def turn_checkpoint_path(*, run_dir: Path, from_turn: int) -> Path:
    """Return checkpoint for durable state after completed turn ``from_turn``.

    The snapshot inside should carry ``next_iteration == from_turn + 1`` so the
    worker resumes at the following turn index.
    """
    turn = int(from_turn)
    if turn < 1:
        raise ValueError("from_turn_must_be_positive")
    return run_dir / TURN_CHECKPOINTS_DIRNAME / f"turn_{turn:04d}.json"


def turn_checkpoint_path_for_next_iteration(*, run_dir: Path, next_iteration: int) -> Path:
    """Map snapshot ``next_iteration`` to the completed-turn checkpoint filename."""
    n = int(next_iteration)
    if n < 2:
        raise ValueError("next_iteration_must_be_at_least_2_for_turn_checkpoint")
    return turn_checkpoint_path(run_dir=run_dir, from_turn=n - 1)
