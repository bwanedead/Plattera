"""Generic delegated-subtask infrastructure for harness orchestration."""

from .contracts import DELEGATE_SUBTASK_ACTION_TYPE
from .registry import DEFAULT_SUBTASK_REGISTRY, SubtaskProfileRegistry

__all__ = [
    "DELEGATE_SUBTASK_ACTION_TYPE",
    "DEFAULT_SUBTASK_REGISTRY",
    "SubtaskProfileRegistry",
]
