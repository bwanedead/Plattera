"""Provider-agnostic LLM call options contract.

Provider adapters map these fields to their API-specific wire format.
Shared between the harness orchestration layer and LLM service adapters.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class LlmCallOptions:
    """Typed structured-output and call options for a single LLM call.

    Passed as ``call_options=<instance>`` kwarg to model callers.
    Provider adapters check for this kwarg and map each field to their
    API-specific settings.  Callers that do not need structured output
    may omit this kwarg entirely.
    """

    # "text" → no special output formatting (provider default)
    # "json_object" → provider-enforced JSON object output
    output_mode: Literal["text", "json_object"] = "text"
    # Image evidence to attach to this call (provider handles multimodal formatting)
    image_attachments: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    # Observability label for logging / tracing
    phase: str | None = None
