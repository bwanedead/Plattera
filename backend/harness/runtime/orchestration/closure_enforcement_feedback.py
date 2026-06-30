"""Generic closure-enforcement block feedback for harness audit/timeline surfaces."""

from __future__ import annotations

from typing import Any, Mapping

POSTURE_AUDIT_PREFIXES = (
    "work_universe_publish_",
    "work_universe_complete_",
    "closure_publish_",
    "closure_complete_",
    "missing_required_output_artifact:",
)

CATEGORY_POSTURE_AUDIT = "publish_posture_audit_gate"
CATEGORY_REAL_BLOCKER = "real_closure_blocker"

POSTURE_AUDIT_REPAIR_HINT = (
    "Local readiness posture blocked execution. Patch mission/closure posture if warranted, "
    "then retry the same action."
)


def classify_closure_enforcement_reason(reason_code: str) -> str:
    code = str(reason_code or "").strip()
    if not code:
        return CATEGORY_REAL_BLOCKER
    if any(code.startswith(prefix) for prefix in POSTURE_AUDIT_PREFIXES):
        return CATEGORY_POSTURE_AUDIT
    if code in {"closure_publish_not_ready", "ready_to_publish_false"}:
        return CATEGORY_POSTURE_AUDIT
    return CATEGORY_REAL_BLOCKER


def closure_enforcement_repair_hint(*, reason_code: str, category: str) -> str:
    if category == CATEGORY_POSTURE_AUDIT:
        return POSTURE_AUDIT_REPAIR_HINT
    return "Resolve the reported closure blocker, then retry the action."


def build_closure_enforcement_block_feedback(
    *,
    blocked_action_id: str,
    reason_code: str,
    message: str | None = None,
    preview_still_valid: bool | None = None,
    next_repair_action: str | None = None,
) -> dict[str, Any]:
    category = classify_closure_enforcement_reason(reason_code)
    feedback: dict[str, Any] = {
        "blocked_action_id": str(blocked_action_id or "").strip() or "unknown",
        "closure_enforcement_reason_code": str(reason_code or "").strip(),
        "blocking_category": category,
        "blocking_categories": [category],
    }
    if message:
        feedback["closure_enforcement_message"] = str(message).strip()
    if preview_still_valid is True:
        feedback["preview_still_valid"] = True
    elif preview_still_valid is False:
        feedback["preview_still_valid"] = False
    elif category == CATEGORY_POSTURE_AUDIT and preview_still_valid is None:
        feedback["preview_still_valid"] = True
    feedback["next_repair_action"] = (
        next_repair_action
        or closure_enforcement_repair_hint(reason_code=str(reason_code or ""), category=category)
    )
    return feedback


def render_closure_enforcement_blocked_timeline_lines(
    feedback: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(feedback, Mapping) or not feedback:
        return []
    lines = [f"{indent}closure_enforcement_blocked:"]
    blocked = feedback.get("blocked_action_id")
    if blocked:
        lines.append(f"{indent}  blocked_action_id: {blocked}")
    reason = feedback.get("closure_enforcement_reason_code")
    if reason:
        lines.append(f"{indent}  reason_code: {reason}")
    category = feedback.get("blocking_category") or feedback.get("publish_gate_category")
    if category:
        lines.append(f"{indent}  blocking_category: {category}")
    categories = feedback.get("blocking_categories")
    if isinstance(categories, list) and categories:
        lines.append(f"{indent}  blocking_categories: {', '.join(str(c) for c in categories[:6])}")
    preview_valid = feedback.get("preview_still_valid")
    if preview_valid is True:
        lines.append(f"{indent}  preview_still_valid: true")
    elif preview_valid is False:
        lines.append(f"{indent}  preview_still_valid: false")
    repair = feedback.get("next_repair_action")
    if repair:
        lines.append(f"{indent}  next_repair_action:")
        lines.extend(_indented_prose(str(repair), indent=f"{indent}    "))
    message = feedback.get("closure_enforcement_message")
    if message:
        lines.append(f"{indent}  message:")
        lines.extend(_indented_prose(str(message), indent=f"{indent}    "))
    return lines


def _indented_prose(text: str, *, indent: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text).splitlines():
        stripped = raw.strip()
        if stripped:
            lines.append(f"{indent}{stripped}")
    if not lines and text.strip():
        lines.append(f"{indent}{text.strip()}")
    return lines
