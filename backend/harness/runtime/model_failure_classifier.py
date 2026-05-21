"""Mechanical classification of model-call transport failures (generic harness)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_USER_ERROR_EXCERPT_CHARS = 400

_SECRET_PATTERNS = (
    re.compile(r"sk-[a-zA-Z0-9]{8,}", re.IGNORECASE),
    re.compile(r"api[_-]?key\s*[:=]\s*\S+", re.IGNORECASE),
    re.compile(r"authorization\s*:\s*\S+", re.IGNORECASE),
)


@dataclass(frozen=True)
class ModelFailureClassification:
    reason_code: str
    resumable: bool
    user_guidance: str
    error_excerpt: str | None = None


# Single source of truth for model-transport resumability (orchestrator, runner, CLI).
_MODEL_TRANSPORT_GUIDANCE: dict[str, str] = {
    "api_quota_exhausted": (
        "API quota or credits appear exhausted. Refill billing/credits, then run resume."
    ),
    "model_connection_interrupted": (
        "Model transport connection was interrupted. Run resume when the network/API path is stable."
    ),
    "model_rate_limited_retryable": (
        "Model rate limit was hit. Wait briefly, then run resume when the API path is stable."
    ),
}

MODEL_RESUMABLE_REASON_CODES: frozenset[str] = frozenset(_MODEL_TRANSPORT_GUIDANCE)


def is_model_transport_resumable_reason(reason_code: str) -> bool:
    return str(reason_code or "").strip() in MODEL_RESUMABLE_REASON_CODES


def bound_error_excerpt(text: str, *, max_chars: int = MAX_USER_ERROR_EXCERPT_CHARS) -> str:
    cleaned = str(text or "").strip()
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub("[redacted]", cleaned)
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3] + "..."


def classify_model_failure(
    *,
    raw_response: Mapping[str, Any] | None = None,
    exception: BaseException | None = None,
) -> ModelFailureClassification:
    """Normalize provider/transport failures into harness reason codes."""
    parts: list[str] = []
    status_code: int | None = None

    if isinstance(raw_response, Mapping):
        parts.append(str(raw_response.get("error") or ""))
        for key in ("status_code", "http_status", "status"):
            raw_status = raw_response.get(key)
            if raw_status is not None:
                try:
                    status_code = int(raw_status)
                except (TypeError, ValueError):
                    pass
                break

    if exception is not None:
        parts.append(str(exception))

    combined = " ".join(part for part in parts if part).strip()
    lowered = combined.lower()
    excerpt = bound_error_excerpt(combined) if combined else None

    # Explicit quota/billing markers before generic HTTP 429 (often rate-limit, not billing).
    if "insufficient_quota" in lowered or (
        "quota" in lowered
        and any(token in lowered for token in ("exhaust", "exceeded", "billing", "credit"))
    ):
        return ModelFailureClassification(
            reason_code="api_quota_exhausted",
            resumable=True,
            user_guidance=_MODEL_TRANSPORT_GUIDANCE["api_quota_exhausted"],
            error_excerpt=excerpt,
        )

    if (
        "rate limit" in lowered
        or "rate_limit" in lowered
        or "too many requests" in lowered
        or status_code == 429
        or " 429 " in f" {combined} "
    ):
        return ModelFailureClassification(
            reason_code="model_rate_limited_retryable",
            resumable=True,
            user_guidance=_MODEL_TRANSPORT_GUIDANCE["model_rate_limited_retryable"],
            error_excerpt=excerpt,
        )

    connection_markers = (
        "connection error",
        "connection reset",
        "connection refused",
        "connection aborted",
        "connect timeout",
        "connection timed out",
        "network is unreachable",
        "temporary failure in name resolution",
        "failed to establish a new connection",
        "remote end closed connection",
    )
    if any(marker in lowered for marker in connection_markers) or (
        isinstance(exception, (ConnectionError, TimeoutError, OSError))
        and "connection" in lowered
    ):
        return ModelFailureClassification(
            reason_code="model_connection_interrupted",
            resumable=True,
            user_guidance=_MODEL_TRANSPORT_GUIDANCE["model_connection_interrupted"],
            error_excerpt=excerpt,
        )

    return ModelFailureClassification(
        reason_code="model_call_failed",
        resumable=False,
        user_guidance="Model call failed before a usable action plan was produced.",
        error_excerpt=excerpt,
    )


def resume_hint_for_reason_code(reason_code: str) -> str | None:
    return _MODEL_TRANSPORT_GUIDANCE.get(str(reason_code or "").strip())
