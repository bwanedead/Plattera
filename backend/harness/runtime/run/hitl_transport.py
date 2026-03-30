from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

HitlState = Literal["no_prompt", "waiting", "answered_unintegrated", "consumed"]


@dataclass
class HitlTransportPosture:
    """Human-in-the-loop transport lifecycle for the bounded orchestrator loop."""

    hitl_state: HitlState = "no_prompt"
    pending_feedback_prompt_id: str | None = None
    pending_feedback_response: dict[str, Any] | None = None
