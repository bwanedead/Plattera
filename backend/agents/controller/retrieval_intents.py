"""Deterministic retrieval intent/query-pack mapping for controller use."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import RetrievalIntent


SEMANTIC_WORKER_UNAVAILABLE_CODES: tuple[str, ...] = (
    "semantic_worker_unavailable",
    "semantic_worker_in_backoff",
    "semantic_worker_timeout",
    "semantic_worker_port_in_use",
    # Legacy alias kept for compatibility.
    "semantic_worker_backoff",
)


@dataclass(frozen=True)
class RetrievalDegradationDecision:
    fallback: str
    reason_code: str
    strategy: str


def map_retrieval_intent_to_inputs(*, intent: RetrievalIntent, query: str) -> dict[str, object]:
    query_text = query.strip()
    limit = 12
    expand = True
    if intent == RetrievalIntent.ANCHOR_HUNT:
        routing = {
            "lanes": ["hybrid", "semantic"],
            "pool": "FINAL_SEGMENTS",
            "view": "final_segments",
        }
    elif intent == RetrievalIntent.DEPENDENCY_HUNT:
        routing = {
            "lanes": ["hybrid", "lexical"],
            "pool": "EVERYTHING",
            "view": "everything",
        }
    elif intent == RetrievalIntent.EXEMPLAR_LOOKUP:
        routing = {
            "lanes": ["semantic"],
            "pool": "EVERYTHING",
            "view": "everything",
            "filters": {"artifact_type": "feature_graph_bundle"},
        }
    elif intent == RetrievalIntent.TERMINOLOGY_CHECK:
        routing = {
            "lanes": ["lexical", "hybrid"],
            "pool": "EVERYTHING",
            "view": "everything",
        }
    else:
        routing = {
            "lanes": ["hybrid"],
            "pool": "EVERYTHING",
            "view": "everything",
        }
    return {
        "query": query_text,
        "intent": intent.value,
        "options": {"limit": limit, "expand": expand},
        "routing": routing,
    }


def classify_retrieval_degradation(reason_code: str) -> RetrievalDegradationDecision | None:
    if reason_code not in SEMANTIC_WORKER_UNAVAILABLE_CODES:
        return None
    if reason_code == "semantic_worker_timeout":
        return RetrievalDegradationDecision(
            fallback="ask_agent",
            reason_code=reason_code,
            strategy="semantic_timeout_requires_new_choice",
        )
    return RetrievalDegradationDecision(
        fallback="lexical",
        reason_code=reason_code,
        strategy="semantic_unavailable_degrade_to_lexical",
    )

