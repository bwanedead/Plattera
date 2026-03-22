"""Phase 26/27: generic orientation JSON contract (no live LLM)."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.agent_kernel.orientation.contract import coerce_generic_orientation_payload


def test_generic_coerce_accepts_empty_items_key_with_candidate_work_items() -> None:
    out = coerce_generic_orientation_payload(
        {
            "items": [],
            "orientation_brief": "This orientation brief is long enough for viability.",
            "candidate_work_items": [
                {
                    "title": "Non-deed work surface",
                    "summary": "Something the model invented that is not a PLSS checklist key.",
                    "suggested_key": "arbitrary_model_key",
                }
            ],
        }
    )
    assert "items" not in out
    assert (
        out["startup_understanding"]["initial_ledger_items"][0].get("suggested_decision_key")
        == "arbitrary_model_key"
    )


def test_generic_coerce_rejects_when_no_startup_signal() -> None:
    with pytest.raises(ValueError, match="orientation_baseline_no_startup_signal"):
        coerce_generic_orientation_payload({"orientation_brief": "tiny"})


def test_generic_coerce_ignores_checklist_items_in_raw_json() -> None:
    """Generic layer does not use transcript checklist rows for viability."""
    with pytest.raises(ValueError, match="orientation_baseline_no_startup_signal"):
        coerce_generic_orientation_payload(
            {
                "items": [
                    {
                        "key": "range",
                        "state": "unknown",
                        "alternatives": ["R74W"],
                        "confidence": "medium",
                        "layer_tag": "layer1_canonical_recovery",
                        "operational_impact": "mapping_blocking",
                        "block_reason": "ambiguity",
                        "required_information": "",
                        "minimal_user_action": "",
                        "resolution_options": [],
                        "self_retrievable": "conditional",
                        "retrieval_attempted": False,
                        "retrieval_blocker": None,
                        "verification_required": True,
                        "attempt_summary": "",
                        "evidence_refs": [],
                    }
                ]
            }
        )
