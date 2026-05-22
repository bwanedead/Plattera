"""Typed contracts for generic delegated subtasks.

These contracts describe mechanical execution rails only.  Profiles frame a
bounded observation task; they do not define mission truth or state mutation.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

DELEGATE_SUBTASK_ACTION_TYPE = "delegate_subtask"

SUBTASK_STATUSES: tuple[str, ...] = (
    "completed",
    "ambiguous",
    "insufficient_input",
    "failed",
)

DEFAULT_MAX_CONTEXT_REFS = 4
DEFAULT_MAX_TASK_CHARS = 1_200
DEFAULT_MAX_RESULT_CHARS = 700
DEFAULT_MAX_OUTPUT_CONTRACT_JSON_CHARS = 1_500
MAX_PROFILE_ID_CHARS = 96
MAX_CONTEXT_REF_CHARS = 256

ResultValidator = Callable[[Mapping[str, Any], "SubtaskProfile"], None]


@dataclass(frozen=True)
class SubtaskModelPolicy:
    """Model selection hook placeholder for a profile.

    ``model_name`` is optional so v1 can use the parent/default model without
    adding escalation policy yet.
    """

    model_name: str | None = None
    phase: str = DELEGATE_SUBTASK_ACTION_TYPE


@dataclass(frozen=True)
class SubtaskBatchingMetadata:
    """Future-facing metadata only; batching is not implemented in V1."""

    supported: bool = False
    max_batch_size: int = 1


@dataclass(frozen=True)
class SubtaskProfile:
    profile_id: str
    owner: str
    description: str
    allowed_ref_kinds: tuple[str, ...]
    prompt_preamble: str
    result_schema: Mapping[str, Any] = field(default_factory=dict)
    result_validator: ResultValidator | None = None
    model_policy: SubtaskModelPolicy = field(default_factory=SubtaskModelPolicy)
    max_context_refs: int = DEFAULT_MAX_CONTEXT_REFS
    max_task_chars: int = DEFAULT_MAX_TASK_CHARS
    max_result_chars: int = DEFAULT_MAX_RESULT_CHARS
    max_turns: int = 1
    batching: SubtaskBatchingMetadata = field(default_factory=SubtaskBatchingMetadata)


@dataclass(frozen=True)
class DelegateSubtaskRequest:
    profile: str
    task: str
    context_refs: tuple[str, ...]
    isolation: Mapping[str, bool] = field(default_factory=dict)
    output_contract: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HydratedSubtaskContext:
    input_refs: tuple[str, ...]
    prompt_ref_summaries: tuple[Mapping[str, Any], ...] = ()
    image_attachments: tuple[dict[str, Any], ...] = ()
    errors: tuple[Mapping[str, Any], ...] = ()
