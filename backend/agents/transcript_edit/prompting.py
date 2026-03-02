from __future__ import annotations

import json
from typing import Any


def build_planner_system_message() -> str:
    return (
        "You are a legal transcript edit planner. "
        "Propose a bounded EditPlanV0 JSON object only. "
        "Faithfully represent source deed semantics, prioritize sanity, and avoid speculative edits. "
        "Do not propose purely cosmetic formatting edits (spacing, punctuation, symbol variants) unless meaning changes. "
        "Prefer localized normalization edits first. "
        "If a finding indicates numeric/PLSS inconsistency and context provides a clear dominant value, "
        "you may propose a localized semantic correction with review_required=true. "
        "Each op must include drift-safe expected_old.old_excerpt from verbatim transcript text. "
        "Prefer anchors locator; use offsets only when anchors are unreliable. "
        "Do not produce cross-section edits unless strictly necessary. "
        "If findings do not justify changes, return an empty ops list with rationale."
    )


def build_planner_user_message(
    *,
    source_transcript_ref: str,
    source_transcript_hash: str,
    findings_summary: dict[str, Any],
    top_findings: list[dict[str, Any]],
    span_context: list[dict[str, Any]],
    image_verification: dict[str, Any],
    candidate_disagreement_hints: dict[str, Any],
    mapping_priority_focus: dict[str, Any],
) -> str:
    schema_snippet = {
        "plan_version": "edit_plan_v0",
        "source_transcript_ref": source_transcript_ref,
        "source_transcript_hash": source_transcript_hash,
        "plan_id": "tx-plan-<id>",
        "summary": "short summary",
        "ops": [
            {
                "op_id": "op-1",
                "op_type": "replace_clause",
                "change_class": "normalization",
                "confidence": "high",
                "review_required": False,
                "reason": "short reason",
                "evidence_refs": [source_transcript_ref],
                "target": {
                    "locator_type": "anchors",
                    "start_anchor": "Beginning at",
                    "end_anchor": "point of beginning",
                    "occurrence": 1,
                },
                "expected_old": {"old_excerpt": "NW", "old_hash": None},
                "new_text": "Northwest",
            }
        ],
        "global_flags": {"review_required": False, "rationale": "optional"},
    }
    payload = {
        "task": "Generate EditPlanV0 JSON only.",
        "constraints": [
            "JSON object only; no markdown.",
            "Every op must include expected_old.old_excerpt copied from transcript.",
            "Anchors preferred; offsets fallback.",
            "Keep edits minimal and faithful to deed semantics.",
        ],
        "schema_snippet": schema_snippet,
        "findings_summary": findings_summary,
        "top_findings": top_findings,
        "span_context": span_context,
        "image_verification": image_verification,
        "candidate_disagreement_hints": candidate_disagreement_hints,
        "mapping_priority_focus": mapping_priority_focus,
    }
    return json.dumps(payload, ensure_ascii=False)


def build_plan_repair_user_message(
    *,
    error_reason: str,
    raw_content: str,
    source_transcript_ref: str,
    source_transcript_hash: str,
) -> str:
    payload = {
        "task": "Repair your previous plan. Return valid EditPlanV0 JSON only.",
        "error_reason": error_reason,
        "previous_output_excerpt": (raw_content or "")[:1200],
        "minimal_valid_example": {
            "plan_version": "edit_plan_v0",
            "source_transcript_ref": source_transcript_ref,
            "source_transcript_hash": source_transcript_hash,
            "plan_id": "tx-plan-repair-1",
            "summary": "example",
            "ops": [],
            "global_flags": {"review_required": False},
        },
        "required_fields": [
            "plan_version",
            "source_transcript_ref",
            "source_transcript_hash",
            "plan_id",
            "summary",
            "ops",
            "global_flags",
        ],
        "note": "If no safe edit is justified, return ops=[] with rationale.",
    }
    return json.dumps(payload, ensure_ascii=False)
