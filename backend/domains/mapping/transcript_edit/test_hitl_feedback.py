from __future__ import annotations

import json
import tempfile
from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.transcript_edit.hitl_feedback import (
    build_human_feedback_prompt,
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


def test_build_human_feedback_prompt_targets_range_contradiction() -> None:
    ledger = {
        "items": [
            {
                "key": "township",
                "label": "Township",
                "state": "unknown",
                "blocking": True,
                "closure_requirement": {
                    "block_reason": "ambiguity",
                    "mapping_blocking": True,
                    "required_information": "Confirm township.",
                    "minimal_user_action": "Choose township.",
                    "resolution_options": ["Township 14 North"],
                    "evidence_refs": [],
                },
            },
            {
                "key": "range",
                "label": "Range",
                "state": "disputed",
                "blocking": True,
                "closure_requirement": {
                    "block_reason": "contradiction",
                    "mapping_blocking": True,
                    "required_information": "Reconcile conflicting range tokens.",
                    "minimal_user_action": "Choose between Range 75 West and Range 74 West.",
                    "resolution_options": ["Range 75 West", "Range 74 West"],
                    "evidence_refs": ["plss_range_conflict_001"],
                },
            },
        ],
        "summary": {"blocking_open_count": 2},
    }
    prompt = build_human_feedback_prompt(decision_ledger=ledger, iteration=2)
    assert isinstance(prompt, dict)
    assert str((prompt.get("context") or {}).get("decision_key") or "") == "range"
    choices = [str(v) for v in list(prompt.get("choices") or [])]
    assert any("75" in v for v in choices)
    assert any("74" in v for v in choices)


def test_build_feedback_override_plan_range_targets_conflicting_occurrence() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "id": "s1",
                            "body": (
                                "Situated in Section Two (2), Township Fourteen (14) North, "
                                "Range seventy-five (75) West; thence ... "
                                "also in Section Two (2), Township Fourteen (14) North, "
                                "Range seventy-four (74) West."
                            ),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        normalized = {
            "decision_key": "range",
            "selected_value": "Range 75 West",
            "note": None,
        }
        plan = build_feedback_override_plan(
            source_transcript_ref=str(source),
            source_transcript_hash="sha256:test",
            normalized_feedback=normalized,
        )
        assert isinstance(plan, dict)
        ops = plan.get("ops") if isinstance(plan.get("ops"), list) else []
        assert len(ops) == 1
        op = ops[0] if isinstance(ops[0], dict) else {}
        assert op.get("op_type") == "replace_span"
        assert (op.get("expected_old") or {}).get("old_excerpt") == "74"
        assert op.get("new_text") == "75"


def test_build_feedback_override_plan_range_supports_compact_r74w_tokens() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "id": "s1",
                            "body": "PLSS tie cites T14N R75W in situate clause but later call cites T14N R74W.",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        normalized = {
            "decision_key": "range",
            "selected_value": "Range 75 West",
            "note": None,
        }
        plan = build_feedback_override_plan(
            source_transcript_ref=str(source),
            source_transcript_hash="sha256:test",
            normalized_feedback=normalized,
        )
        assert isinstance(plan, dict)
        ops = plan.get("ops") if isinstance(plan.get("ops"), list) else []
        assert len(ops) == 1
        op = ops[0] if isinstance(ops[0], dict) else {}
        assert (op.get("expected_old") or {}).get("old_excerpt") == "74"
        assert op.get("new_text") == "75"


def test_build_feedback_override_plan_range_parses_selected_value_with_75w_shorthand() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "source.json"
        source.write_text(
            json.dumps(
                {
                    "sections": [
                        {
                            "id": "s1",
                            "body": (
                                "Situated in T14N Range Seventy-five (75) West, "
                                "but later calls cite Range Seventy-four (74) West."
                            ),
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        normalized = {
            "decision_key": "range",
            "selected_value": "Use Range 75W as controlling and treat Range 74W as clerical error.",
            "note": None,
        }
        plan = build_feedback_override_plan(
            source_transcript_ref=str(source),
            source_transcript_hash="sha256:test",
            normalized_feedback=normalized,
        )
        assert isinstance(plan, dict)
        op = plan["ops"][0]
        assert (op.get("expected_old") or {}).get("old_excerpt") == "74"
        assert op.get("new_text") == "75"


def test_build_human_feedback_prompt_includes_focused_image_evidence_refs_when_available() -> None:
    ledger = {
        "items": [
            {
                "key": "range",
                "label": "Range",
                "state": "disputed",
                "blocking": True,
                "closure_requirement": {
                    "block_reason": "contradiction",
                    "mapping_blocking": True,
                    "required_information": "Reconcile range token.",
                    "minimal_user_action": "Pick the correct range value.",
                    "resolution_options": ["Range 74 West", "Range 75 West"],
                    "evidence_refs": ["plss_range_conflict_001"],
                },
            }
        ]
    }
    prompt = build_human_feedback_prompt(
        decision_ledger=ledger,
        iteration=4,
        image_verification_payload={
            "results": [
                {
                    "check_id": "plss_range_conflict_001",
                    "decision_key": "range",
                    "status": "unclear",
                    "tx_image_evidence_region_ref": {"artifact_path": "in-memory://region.jpg"},
                    "tx_image_evidence_context_ref": {"artifact_path": "in-memory://context.jpg"},
                }
            ]
        },
    )
    assert isinstance(prompt, dict)
    context = prompt.get("context") if isinstance(prompt.get("context"), dict) else {}
    evidence = context.get("focused_image_evidence") if isinstance(context.get("focused_image_evidence"), dict) else {}
    assert isinstance(evidence.get("tx_image_evidence_region_ref"), dict)
    assert str((evidence.get("tx_image_evidence_region_ref") or {}).get("artifact_path") or "") == "in-memory://region.jpg"


def test_build_human_feedback_prompt_prefers_visual_evidence_state_refs_when_available() -> None:
    ledger = {
        "items": [
            {
                "key": "range",
                "label": "Range",
                "state": "disputed",
                "blocking": True,
                "closure_requirement": {
                    "block_reason": "contradiction",
                    "mapping_blocking": True,
                    "required_information": "Reconcile range token.",
                    "minimal_user_action": "Pick the correct range value.",
                    "resolution_options": ["Range 74 West", "Range 75 West"],
                    "evidence_refs": ["plss_range_conflict_001"],
                },
            }
        ]
    }
    prompt = build_human_feedback_prompt(
        decision_ledger=ledger,
        iteration=4,
        image_verification_payload={
            "results": [
                {
                    "check_id": "plss_range_conflict_001",
                    "decision_key": "range",
                    "status": "unclear",
                    "tx_image_evidence_region_ref": {"artifact_path": "in-memory://old-region.jpg"},
                }
            ]
        },
        visual_evidence_state={
            "check_id": "locate_range_2",
            "status": "located",
            "query": "Locate range clause",
            "tx_image_evidence_region_ref": {"artifact_path": "in-memory://new-region.jpg"},
            "tx_image_evidence_context_ref": {"artifact_path": "in-memory://new-context.jpg"},
        },
    )
    assert isinstance(prompt, dict)
    context = prompt.get("context") if isinstance(prompt.get("context"), dict) else {}
    evidence = context.get("focused_image_evidence") if isinstance(context.get("focused_image_evidence"), dict) else {}
    assert str((evidence.get("tx_image_evidence_region_ref") or {}).get("artifact_path") or "") == "in-memory://new-region.jpg"

