from __future__ import annotations

import dataclasses
import enum
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from collections.abc import Callable, Mapping

from .contracts import OrchestratorContext, SharedStateProjection
from .trace_collector import KernelTraceCollector


class PreChooseActionParticipant(Protocol):
    """Explicit mechanical participant that may run before choose_action."""

    def before_choose_action(
        self,
        context: OrchestratorContext,
        projection: SharedStateProjection | None,
        *,
        tracer: KernelTraceCollector,
    ) -> None: ...


class PromptEventObserver(Protocol):
    """Observer for prompt-event identity metadata emitted by model-facing lanes."""

    def observe_prompt_event(self, info: dict[str, Any]) -> None: ...


class RawLlmIoObserver(Protocol):
    """Observer for per-turn raw LLM I/O audit records."""

    def observe_llm_io(self, record: dict[str, Any]) -> None: ...


class TurnCompletionObserver(Protocol):
    """Observer for post-turn mechanical completion records."""

    def observe_turn_completed(self, record: dict[str, Any]) -> None: ...


@dataclass(frozen=True)
class OrchestrationLifecycle:
    """Explicit mechanical lifecycle bundle for the orchestration runtime."""

    pre_choose_action_participant: PreChooseActionParticipant | None = None
    prompt_event_observer: PromptEventObserver | None = None
    raw_llm_io_observer: RawLlmIoObserver | None = None
    turn_completion_observer: TurnCompletionObserver | None = None
    resume_checkpoint_writer: Callable[[Mapping[str, Any]], None] | None = None


class KernelPromptEventTraceObserver:
    """Turn structured prompt-event metadata into canonical trace events."""

    def __init__(self, *, tracer: KernelTraceCollector) -> None:
        self._tracer = tracer

    def observe_prompt_event(self, info: dict[str, Any]) -> None:
        raw_iter = info.get("iteration")
        iteration_index: int | None = int(raw_iter) if isinstance(raw_iter, int) else None
        prompt_event = info.get("prompt_event")
        if not isinstance(prompt_event, dict):
            return
        metadata = prompt_event.get("metadata") if isinstance(prompt_event.get("metadata"), dict) else {}
        self._tracer.emit_prompt_event(
            iteration=iteration_index,
            prompt_event=prompt_event,
            surface=str(metadata.get("surface") or info.get("surface") or ""),
            pack_id=_pack_id_from_prompt_metadata(metadata, info),
            model=str(metadata.get("model") or info.get("model") or ""),
        )


def _pack_id_from_prompt_metadata(metadata: dict[str, Any], info: dict[str, Any]) -> str:
    """Prompt-pack identifier from metadata (``pack_id`` only)."""
    return str(metadata.get("pack_id") or info.get("pack_id") or "")


def lifecycle_jsonable(value: Any) -> Any:
    """Normalize lifecycle payloads into explicit JSON-safe mechanical records."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if hasattr(value, "model_dump") and callable(value.model_dump):
        try:
            return lifecycle_jsonable(value.model_dump(mode="json"))
        except Exception as exc:
            return {"repr_fallback": repr(value), "serialization_error": str(exc)}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        try:
            return lifecycle_jsonable(dataclasses.asdict(value))
        except Exception as exc:
            return {"repr_fallback": repr(value), "serialization_error": str(exc)}
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): lifecycle_jsonable(raw_value) for key, raw_value in value.items()}
    if isinstance(value, (list, tuple)):
        return [lifecycle_jsonable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [lifecycle_jsonable(item) for item in sorted(value, key=str)]
    return {"repr_fallback": repr(value)}
