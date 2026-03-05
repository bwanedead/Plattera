from __future__ import annotations

from typing import Any

from .decision_ledger import unresolved_mapping_blocking_requirements


def blocking_unresolved_count(ledger: dict[str, Any] | None) -> int:
    return len(unresolved_mapping_blocking_requirements(ledger))


def blocking_signature(ledger: dict[str, Any] | None) -> str:
    unresolved = unresolved_mapping_blocking_requirements(ledger)
    parts: list[str] = []
    for item in unresolved:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "").strip().lower()
        state = str(item.get("state") or "unknown").strip().lower()
        requirement = item.get("closure_requirement") if isinstance(item.get("closure_requirement"), dict) else {}
        block_reason = str(requirement.get("block_reason") or "ambiguity").strip().lower()
        selected_value = str((item.get("selected_value") or "")).strip().lower()
        parts.append(f"{key}:{state}:{block_reason}:{selected_value}")
    parts.sort()
    return "|".join(parts)


def classify_iteration_progress(
    *,
    previous_finding_signature: str | None,
    current_finding_signature: str,
    previous_blocking_signature: str | None,
    current_blocking_signature: str,
    previous_blocking_count: int | None,
    current_blocking_count: int,
    previous_signal_counter: int,
    current_signal_counter: int,
    pending_feedback_prompt_id: str | None,
    pending_reaudit_after_apply: bool,
    apply_reaudit_baseline_blocking_count: int | None,
) -> tuple[bool, str, bool]:
    if pending_reaudit_after_apply:
        baseline = int(apply_reaudit_baseline_blocking_count if apply_reaudit_baseline_blocking_count is not None else current_blocking_count)
        if current_blocking_count < baseline:
            return True, "apply_reaudit_improved_blocking_closure", True
        return False, "apply_reaudit_no_blocking_improvement", True

    if current_signal_counter > previous_signal_counter:
        return True, "new_signal_arrived", False

    if previous_finding_signature is None or previous_blocking_signature is None:
        return True, "initial_iteration_baseline", False

    prev_count = int(previous_blocking_count if previous_blocking_count is not None else current_blocking_count)
    if current_blocking_count < prev_count:
        return True, "blocking_count_reduced", False
    if current_blocking_signature != previous_blocking_signature and current_blocking_count <= prev_count:
        return True, "blocking_state_changed", False
    if current_finding_signature != previous_finding_signature and current_blocking_count <= prev_count:
        return True, "audit_signature_changed", False

    if pending_feedback_prompt_id:
        return False, "pending_human_feedback_no_new_signal", False
    return False, "no_material_change", False
