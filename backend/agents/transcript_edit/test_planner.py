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


def test_planner_focus_move_falls_back_to_mark_blocked_for_invalid_apply_under_answered_ticket() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"apply_edit_plan","reason":"try_apply","iteration_summary":"x",'
                '"edit_plan":{"plan_version":"edit_plan_v0","source_transcript_ref":"in-memory://source.json",'
                '"source_transcript_hash":"sha256:test","plan_id":"p1","summary":"s",'
                '"ops":[{"op_id":"op-1","change_class":"semantic","confidence":"high","review_required":true,'
                '"reason":"r","evidence_refs":[],"target":{"locator_type":"offsets","start_char":0,"end_char":1},'
                '"expected_old":{"old_excerpt":"a"},"new_text":"b"}],"global_flags":{"review_required":true}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok_post_feedback_fallback"
    assert isinstance(payload, dict)
    assert payload.get("move") == "mark_blocked"
    assert str(payload.get("reason") or "").startswith("blocked_no_safe_integration_after_feedback")


def test_planner_preserves_image_evidence_select_region_target_fields() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"inspect_range","iteration_summary":"select first",'
                '"evidence_request":{"kind":"image_evidence","mode":"select_region","decision_key":"range","reason":"pick region",'
                '"target":{"crop_box_normalized":{"x":0.2,"y":0.3,"width":0.4,"height":0.2},"zoom_factor":2.2,"expected_fields":["range"]}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok"
    assert isinstance(payload, dict)
    evidence = payload.get("evidence_request") if isinstance(payload.get("evidence_request"), dict) else {}
    target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
    assert str(evidence.get("mode") or "") == "select_region"
    assert isinstance(target.get("crop_box_normalized"), dict)
    assert target.get("zoom_factor") == 2.2


def test_planner_normalizes_image_evidence_target_mode_form() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"inspect_range","iteration_summary":"select via target mode",'
                '"evidence_request":{"kind":"image_evidence","decision_key":"range","reason":"pick region",'
                '"target":{"mode":"select_region","crop_box_normalized":{"x":0.2,"y":0.3,"width":0.4,"height":0.2}}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok"
    assert isinstance(payload, dict)
    evidence = payload.get("evidence_request") if isinstance(payload.get("evidence_request"), dict) else {}
    target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
    assert str(evidence.get("mode") or "") == "select_region"
    assert target.get("mode") is None
    assert isinstance(target.get("crop_box_normalized"), dict)


def test_planner_normalizes_image_evidence_operation_key_form() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"inspect_range","iteration_summary":"select via operation key",'
                '"evidence_request":{"kind":"image_evidence","decision_key":"range","reason":"pick region",'
                '"target":{"select_region":{"crop_box_normalized":{"x":0.15,"y":0.25,"width":0.35,"height":0.2}}}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok"
    assert isinstance(payload, dict)
    evidence = payload.get("evidence_request") if isinstance(payload.get("evidence_request"), dict) else {}
    target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
    assert str(evidence.get("mode") or "") == "select_region"
    assert isinstance(target.get("crop_box_normalized"), dict)


def test_planner_normalizes_image_evidence_operation_key_refine_form() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"refine_region","iteration_summary":"refine via operation key",'
                '"evidence_request":{"kind":"image_evidence","decision_key":"range","reason":"tighten region",'
                '"target":{"refine_region":{"region_ref":{"artifact_path":"in-memory://region.jpg"},"transform":"expand","amount":0.2}}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok"
    assert isinstance(payload, dict)
    evidence = payload.get("evidence_request") if isinstance(payload.get("evidence_request"), dict) else {}
    target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
    assert str(evidence.get("mode") or "") == "refine_region"
    assert isinstance(target.get("region_ref"), dict)
    assert str(target.get("transform") or "") == "expand"


def test_planner_normalizes_refine_region_crop_shorthand_to_select_region() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"refine_with_crop","iteration_summary":"tighten crop",'
                '"evidence_request":{"kind":"image_evidence","decision_key":"range","reason":"tighten around range token",'
                '"target":{"mode":"refine_region","crop_box_normalized":{"x":0.4,"y":0.18,"width":0.32,"height":0.14},"zoom_factor":3.0,"expected_fields":["range"]}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=2,
    )
    assert reason == "ok"
    assert isinstance(payload, dict)
    evidence = payload.get("evidence_request") if isinstance(payload.get("evidence_request"), dict) else {}
    target = evidence.get("target") if isinstance(evidence.get("target"), dict) else {}
    assert str(evidence.get("mode") or "") == "select_region"
    assert isinstance(target.get("crop_box_normalized"), dict)
    assert target.get("zoom_factor") == 3.0


def test_planner_rejects_conflicting_image_evidence_mode_sources() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"conflict","iteration_summary":"bad",'
                '"evidence_request":{"kind":"image_evidence","mode":"verify_region","decision_key":"range","target":{"mode":"select_region","crop_box_normalized":{"x":0.2,"y":0.2,"width":0.3,"height":0.2}}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=1,
    )
    assert payload is None
    assert "image_evidence_mode_conflict" in reason


def test_planner_rejects_multiple_nested_image_evidence_operation_keys() -> None:
    service = _FakeService(
        outputs=[
            (
                '{"decision_key":"range","move":"gather_more_evidence","reason":"ambiguous","iteration_summary":"bad",'
                '"evidence_request":{"kind":"image_evidence","decision_key":"range","target":{"select_region":{"crop_box_normalized":{"x":0.2,"y":0.2,"width":0.3,"height":0.2}},"verify_region":{"region_ref":{"artifact_path":"in-memory://region.jpg"},"query":"verify"}}}}'
            )
        ]
    )
    planner = TranscriptEditPlanPlanner(service=service)
    payload, reason, _raw = planner.propose_focus_move(
        model="gpt-5.2",
        focus_packet=_focus_packet_with_answered_ticket(),
        max_attempts=1,
    )
    assert payload is None
    assert "image_evidence_target_mode_ambiguous" in reason
