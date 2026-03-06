from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.agents.transcript_edit.planner import TranscriptEditPlanPlanner


class _FakeCompletions:
    def __init__(self, outputs: list[str]) -> None:
        self._outputs = list(outputs)
        self.calls: list[dict] = []

    def create(self, **params):  # type: ignore[no-untyped-def]
        self.calls.append(params)
        content = self._outputs.pop(0) if self._outputs else "{}"
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _FakeService:
    def __init__(self, outputs: list[str]) -> None:
        self.models = {"gpt-5.2": {"api_model_name": "gpt-5.2"}}
        self._completions = _FakeCompletions(outputs)
        self.client = SimpleNamespace(
            chat=SimpleNamespace(completions=self._completions)
        )

    def is_available(self) -> bool:
        return True


def _focus_packet_with_answered_ticket() -> dict:
    return {
        "decision_key": "range",
        "source_transcript_ref": "in-memory://source.json",
        "source_transcript_hash": "sha256:test",
        "external_context_injections": [
            {
                "type": "human_resolution_ticket",
                "ticket_id": "hitl_range_1_test",
                "decision_key": "range",
                "lifecycle_state": "answered_unintegrated",
                "strength": "binding",
                "payload": {
                    "normalized_answer_summary": "Range 75 West",
                    "selected_choice": "Range 75 West",
                },
            }
        ],
    }


def test_planner_focus_move_recovers_after_one_invalid_output_with_injected_ticket_context() -> None:
    service = _FakeService(
        outputs=[
            '{"move":"bad"}',
            '{"decision_key":"range","move":"mark_blocked","reason":"no_safe_plan","iteration_summary":"blocked"}',
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok"
    assert isinstance(payload, dict)
    assert payload["move"] == "mark_blocked"
    assert raw.strip().startswith("{")
    assert len(service._completions.calls) == 2
    second_call = service._completions.calls[1]
    repair_user_msg = str(second_call["messages"][1]["content"])
    assert "injection_context" in repair_user_msg
    assert "answered_unintegrated" in repair_user_msg


def test_planner_focus_move_exhausts_after_repeated_invalid_output() -> None:
    service = _FakeService(outputs=['{"move":"bad"}', '{"still":"bad"}'])
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert payload is None
    assert reason.startswith("resolver_invalid:")
    assert "invalid_move" in reason or "missing" in reason.lower()
    assert raw.strip().startswith("{")
