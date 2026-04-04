from __future__ import annotations

from dataclasses import dataclass


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

    def register_llm_contact(self) -> None:
        self.llm_contact_count += 1

    def register_prompt_event(self, *, prompt_event_id: str | None, surface: str | None) -> None:
        self.prompt_event_count += 1
        if isinstance(prompt_event_id, str) and prompt_event_id.strip():
            self.last_prompt_event_id = prompt_event_id.strip()
        if isinstance(surface, str) and surface.strip():
            self.last_prompt_event_surface = surface.strip()
