"""Resumable model transport interruptions (checkpoint + paused terminal)."""

from __future__ import annotations

from typing import Any

from ..model_failure_classifier import ModelFailureClassification


class ResumableModelInterruption(RuntimeError):
    """Model call failed in a way that should pause the run for operator resume."""

    def __init__(
        self,
        *,
        classification: ModelFailureClassification,
        iteration: int,
        prompt_mode: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.reason_code = classification.reason_code
        self.terminal_summary = classification.user_guidance
        self.user_guidance = classification.user_guidance
        self.failure_record: dict[str, Any] = {
            "iteration": int(iteration),
            "prompt_mode": str(prompt_mode),
            "reason_code": classification.reason_code,
            "message": classification.error_excerpt or classification.user_guidance,
            "user_guidance": classification.user_guidance,
            "resumable": True,
        }
        if extra:
            self.failure_record.update(extra)
        super().__init__(classification.user_guidance)
