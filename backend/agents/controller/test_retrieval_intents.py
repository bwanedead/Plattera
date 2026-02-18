from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.controller.contracts import RetrievalIntent
from backend.agents.controller.retrieval_intents import (
    SEMANTIC_WORKER_UNAVAILABLE_CODES,
    classify_retrieval_degradation,
    map_retrieval_intent_to_inputs,
)


def test_retrieval_reason_code_table_includes_canonical_and_legacy_codes() -> None:
    assert "semantic_worker_unavailable" in SEMANTIC_WORKER_UNAVAILABLE_CODES
    assert "semantic_worker_in_backoff" in SEMANTIC_WORKER_UNAVAILABLE_CODES
    assert "semantic_worker_timeout" in SEMANTIC_WORKER_UNAVAILABLE_CODES
    assert "semantic_worker_port_in_use" in SEMANTIC_WORKER_UNAVAILABLE_CODES
    assert "semantic_worker_backoff" in SEMANTIC_WORKER_UNAVAILABLE_CODES


def test_retrieval_degradation_mapping_is_deterministic() -> None:
    timeout = classify_retrieval_degradation("semantic_worker_timeout")
    unavailable = classify_retrieval_degradation("semantic_worker_in_backoff")

    assert timeout is not None
    assert timeout.fallback == "ask_agent"
    assert unavailable is not None
    assert unavailable.fallback == "lexical"


def test_map_retrieval_intent_to_inputs_builds_query_pack() -> None:
    payload = map_retrieval_intent_to_inputs(
        intent=RetrievalIntent.ANCHOR_HUNT,
        query="find section corner tie",
    )

    assert payload["intent"] == RetrievalIntent.ANCHOR_HUNT.value
    assert payload["query"] == "find section corner tie"
    assert payload["routing"]["pool"] == "FINAL_SEGMENTS"

