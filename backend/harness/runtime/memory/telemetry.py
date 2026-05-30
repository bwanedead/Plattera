from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PromptContactTelemetry:
    """Mechanical counts and last identifiers for model-facing observability.

    ``llm_contact_count`` increments once per model contact (including contacts that are also
    recorded as a full ``prompt_event``). ``prompt_event_count`` increments when the trace path
    carries a structured ``prompt_event`` payload (kernel LLM turns use both).

    Must not gate loop control or semantic decisions (Harness Constitution).
    """

    llm_contact_count: int = 0
    prompt_event_count: int = 0
    last_prompt_event_id: str | None = None
    last_prompt_event_surface: str | None = None
    turn_contact_records: list[dict[str, Any]] = field(default_factory=list)

    def register_llm_contact(self) -> None:
        self.llm_contact_count += 1

    def register_prompt_event(self, *, prompt_event_id: str | None, surface: str | None) -> None:
        self.prompt_event_count += 1
        if isinstance(prompt_event_id, str) and prompt_event_id.strip():
            self.last_prompt_event_id = prompt_event_id.strip()
        if isinstance(surface, str) and surface.strip():
            self.last_prompt_event_surface = surface.strip()

    def register_turn_contact(
        self,
        *,
        turn_index: int,
        prompt_char_count: int,
        started_at_epoch_seconds: float,
        finished_at_epoch_seconds: float,
        resolution_state_before: Mapping[str, Any] | None = None,
    ) -> None:
        """Append mechanical per-turn contact facts for performance evaluation."""
        record: dict[str, Any] = {
            "turn_index": int(turn_index),
            "prompt_char_count": int(prompt_char_count),
            "started_at_epoch_seconds": float(started_at_epoch_seconds),
            "finished_at_epoch_seconds": float(finished_at_epoch_seconds),
        }
        if isinstance(resolution_state_before, Mapping):
            record["resolution_state_before"] = dict(resolution_state_before)
        self.turn_contact_records.append(record)

    def finalize_turn_contact(
        self,
        *,
        turn_index: int,
        finished_at_epoch_seconds: float | None = None,
        resolution_state_after: Mapping[str, Any] | None,
        delegate_count: int = 0,
        determinations_changed: int | None = None,
        units_closed: int | None = None,
    ) -> None:
        """Attach post-execution mechanical facts to the matching turn contact row."""
        for row in reversed(self.turn_contact_records):
            if int(row.get("turn_index") or -1) != int(turn_index):
                continue
            if finished_at_epoch_seconds is not None:
                row["finished_at_epoch_seconds"] = float(finished_at_epoch_seconds)
            if isinstance(resolution_state_after, Mapping):
                row["resolution_state_after"] = dict(resolution_state_after)
            row["delegate_count"] = int(delegate_count)
            if determinations_changed is not None:
                row["determinations_changed"] = int(determinations_changed)
            if units_closed is not None:
                row["units_closed"] = int(units_closed)
            return
