from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from tooling.mapping.transcription_edit.contracts import EditPlanV0
from services.workflows.mapping.transcription_edit.persistence import TranscriptionEditPersistenceService
from tooling.mapping.transcription_edit.span_seeds import load_transcript_text_for_seeds


def coerce_findings(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in values[:12]:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "finding_id": item.get("finding_id"),
                "finding_type": item.get("finding_type"),
                "severity": item.get("severity"),
                "message": item.get("message"),
                "section_id": item.get("section_id"),
                "span": item.get("span"),
            }
        )
    return out


def finding_signature(*, summary: dict[str, Any], findings: list[dict[str, Any]]) -> str:
    payload = {
        "summary": summary,
        "findings": [
            {
                "finding_id": f.get("finding_id"),
                "severity": f.get("severity"),
                "finding_type": f.get("finding_type"),
            }
            for f in findings[:8]
            if isinstance(f, dict)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def max_change_class_from_plan(plan: dict[str, Any]) -> str:
    ops = plan.get("ops")
    if not isinstance(ops, list):
        return "normalization"
    rank = {"normalization": 0, "semantic": 1, "structural": 2}
    highest = 0
    for op in ops:
        if not isinstance(op, dict):
            continue
        cc = str(op.get("change_class") or "").strip().lower()
        highest = max(highest, rank.get(cc, 0))
    for key, value in rank.items():
        if value == highest:
            return key
    return "normalization"


def plan_has_review_required(plan: dict[str, Any]) -> bool:
    flags = plan.get("global_flags")
    if isinstance(flags, dict) and bool(flags.get("review_required")):
        return True
    ops = plan.get("ops")
    if isinstance(ops, list):
        for op in ops:
            if isinstance(op, dict) and bool(op.get("review_required")):
                return True
    return False


def plan_has_no_ops(plan: dict[str, Any]) -> bool:
    ops = plan.get("ops")
    if not isinstance(ops, list):
        return True
    return len([op for op in ops if isinstance(op, dict)]) == 0


def build_apply_inputs_for_plan(
    *,
    persistence: TranscriptionEditPersistenceService,
    dossier_id: str | None,
    plan_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    out: dict[str, Any] = {"dossier_id": dossier_id}
    if not isinstance(plan_payload, dict):
        return out
    try:
        plan = EditPlanV0.model_validate(plan_payload)
    except Exception:
        out["edit_plan"] = plan_payload
        return out
    try:
        plan_ref = persistence.save_edit_plan(dossier_id=dossier_id or "adhoc", plan=plan)
    except Exception:
        out["edit_plan"] = plan.model_dump(mode="json")
        return out
    out["edit_plan_ref"] = plan_ref
    return out


def top_findings_summary_text(findings: list[dict[str, Any]]) -> str:
    msgs: list[str] = []
    for f in findings[:3]:
        if not isinstance(f, dict):
            continue
        msg = str(f.get("message") or "").strip()
        if msg:
            msgs.append(msg[:120])
    return "; ".join(msgs) if msgs else ""


def finding_to_display_dict(finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "finding_id": finding.get("finding_id"),
        "finding_type": finding.get("finding_type"),
        "severity": finding.get("severity"),
        "message": str(finding.get("message") or "")[:200],
    }


_RANGE_TOKEN_RE = re.compile(r"Range\s+(\d+)\s+West", re.IGNORECASE)


def load_working_transcript_text(source_transcript_ref: str) -> str:
    """Load flattened transcript text from an artifact path (same shape as span seed loader)."""
    raw = load_transcript_text_for_seeds(source_transcript_ref)
    return raw or ""


def _range_digit_from_fragment(text: str) -> int | None:
    m = _RANGE_TOKEN_RE.search(text or "")
    return int(m.group(1)) if m else None


def validate_edit_plan_directionality(
    *,
    plan: EditPlanV0,
    transcript_text: str,
    feedback: dict[str, Any] | None,
    injection_context: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    """Reject edit plans that invert a known range correction when HITL supplied the correct value.

    Phase 22: HITL may include a locator-style excerpt of the *wrong* token; that excerpt must
    become expected_old, not new_text. When selected_value contains an authoritative
    \"Range N West\" choice, ensure the plan does not remove the correct N.
    """
    auth = ""
    if isinstance(feedback, dict):
        auth = str(feedback.get("selected_value") or feedback.get("choice") or "").strip()
    inj = injection_context if isinstance(injection_context, dict) else {}
    if not auth and isinstance(inj, dict):
        auth = str(inj.get("normalized_answer_summary") or inj.get("selected_choice") or "").strip()
    correct_n = _range_digit_from_fragment(auth)

    for op in plan.ops:
        old_excerpt = str(op.expected_old.old_excerpt or "").strip()
        new_t = str(op.new_text or "").strip()
        if old_excerpt and old_excerpt not in transcript_text:
            return False, "expected_old_not_in_working_transcript"
        if correct_n is None:
            continue
        old_n = _range_digit_from_fragment(old_excerpt)
        new_n = _range_digit_from_fragment(new_t)
        if old_n is None and new_n is None:
            continue
        # Inverted correction: plan removes the authoritative correct range value from the transcript.
        if old_n == correct_n and new_n is not None and new_n != correct_n:
            return False, "plan_removes_authoritative_range_value"
        # Swapped direction: replacing correct token with the disputed wrong token.
        # Legitimate repair: replace a non-authoritative old token with the authoritative range value.
        if new_n == correct_n and old_n is not None and old_n != correct_n:
            continue
    return True, None


def plan_op_to_display_dict(op: dict[str, Any]) -> dict[str, Any]:
    original = str(op.get("expected_old", {}).get("old_excerpt", "") if isinstance(op.get("expected_old"), dict) else "")
    replacement = str(op.get("new_text") or "")
    return {
        "op_type": op.get("op_type"),
        "reason": str(op.get("reason") or "")[:100],
        "original_text": original[:50] + ("..." if len(original) > 50 else ""),
        "replacement_text": replacement[:50] + ("..." if len(replacement) > 50 else ""),
    }




