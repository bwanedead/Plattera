from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.planner import TranscriptEditPlanPlanner


class _FakeCompletions:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[dict[str, object]] = []

    def create(self, **params):  # type: ignore[no-untyped-def]
        self.calls.append(params)
        content = self._outputs.pop(0) if self._outputs else "{}"
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


class _FakeService:
    def __init__(self, outputs: list[str]) -> None:
        self.models = {"gpt-5.2": {"api_model_name": "gpt-5.2"}}
        self._completions = _FakeCompletions(outputs)
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=self._completions))

    def is_available(self) -> bool:
        return True


def test_planner_propose_plan_emits_prompt_event_metadata_and_source_blocks() -> None:
    calls: list[dict[str, object]] = []
    planner = TranscriptEditPlanPlanner(service=_FakeService(outputs=["{}"]), identity_trace_cb=calls.append)

    plan, reason, raw = planner.propose_plan(
        model="gpt-5.2",
        source_transcript_ref="in-memory://source.json",
        source_transcript_hash="sha256:test",
        findings_summary={},
        top_findings=[],
        span_context=[],
        image_verification=None,
        candidate_disagreement_hints=None,
        mapping_priority_focus=None,
        max_attempts=1,
    )

    assert plan is None
    assert reason.startswith("plan_invalid:")
    assert raw.strip() == "{}"
    assert len(calls) == 2
    identity_payload = calls[0]
    prompt_payload = calls[1]
    assert identity_payload["surface"] == "tx_planner"
    assert identity_payload["domain"] == "transcript_edit"
    assert identity_payload["prompt_event_metadata"]["surface"] == "tx_planner"
    assert identity_payload["prompt_event_metadata"]["domain"] == "transcript_edit"
    assert "prompt_event" not in identity_payload
    assert prompt_payload["surface"] == "tx_planner"
    assert prompt_payload["domain"] == "transcript_edit"
    assert prompt_payload["prompt_event_metadata"]["surface"] == "tx_planner"
    assert prompt_payload["prompt_event_metadata"]["domain"] == "transcript_edit"
    assert "prompt_event" in prompt_payload
    prompt_event = prompt_payload["prompt_event"]
    assert prompt_event["outcome_kind"] == "plan_invalid"
    owners = {row["owner"] for row in identity_payload["source_blocks"]}
    assert "shared_harness" in owners
    assert "transcript_edit" in owners

