"""Phase 27: transcript-edit orientation adapter (checklist) vs generic contract."""
from __future__ import annotations

from domains.mapping.transcript_edit.orient_checklist_adapter import (
    coerce_transcript_edit_checklist_seed_items,
    coerce_transcript_edit_orient_payload,
)


def test_transcript_adapter_accepts_checklist_only_payload() -> None:
    out = coerce_transcript_edit_orient_payload(
        {
            "items": [
                {
                    "key": "range",
                    "state": "unknown",
                    "alternatives": ["R74W", "R75W"],
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
    assert len(out["checklist_seed_items"]) == 1
    assert out["checklist_seed_items"][0].get("key") == "range"


def test_checklist_adapter_filters_unknown_keys() -> None:
    raw = {
        "items": [
            {"key": "range", "state": "unknown"},
            {"key": "custom_model_key", "state": "unknown"},
        ]
    }
    rows = coerce_transcript_edit_checklist_seed_items(raw)
    assert len(rows) == 1
    assert rows[0].get("key") == "range"


def test_transcript_adapter_merges_generic_work_with_arbitrary_suggested_key() -> None:
    out = coerce_transcript_edit_orient_payload(
        {
            "orientation_brief": "This orientation brief is long enough for viability.",
            "candidate_work_items": [
                {
                    "title": "Domain-specific surface",
                    "summary": "Not a deed checklist key.",
                    "suggested_key": "model_authored_key_xyz",
                }
            ],
        }
    )
    assert out["checklist_seed_items"] == []
    assert (
        out["startup_understanding"]["initial_ledger_items"][0].get("suggested_decision_key")
        == "model_authored_key_xyz"
    )

