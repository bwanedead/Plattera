from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.hitl_feedback import (
    build_feedback_override_plan,
    normalize_feedback_response,
)


def test_normalize_feedback_prefers_prompt_context_decision_key() -> None:
    feedback_entry = {
        "prompt_id": "hitl_section_1_abcd1234",
        "choice": "Section 12",
        "note": "Resolved section as: Section 12",
        "metadata": {"action": "prompt_feedback"},
    }
    normalized = normalize_feedback_response(
        feedback_entry=feedback_entry,
        prompt_id="hitl_section_1_abcd1234",
        prompt_context={"decision_key": "section"},
    )
    assert isinstance(normalized, dict)
    assert normalized["decision_key"] == "section"
    assert str(normalized["selected_value"]) == "Section 12"


def test_build_feedback_override_plan_fails_safely_when_no_target_match() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps({"sections": [{"id": "s1", "body": "No section token present in this transcript."}]}),
            encoding="utf-8",
        )
        normalized = {
            "decision_key": "section",
            "selected_value": "Section 12",
            "note": None,
        }
        plan = build_feedback_override_plan(
            source_transcript_ref=str(source),
            source_transcript_hash="sha256:test",
            normalized_feedback=normalized,
        )
        assert plan is None
