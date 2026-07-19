"""Contain retired prepare/publish action guidance at the finalizer boundary.

Internal prepare/publish implementations may still emit legacy action IDs or
prepare/publish workflow prose in refusal payloads. Agent-visible finalizer
results must never instruct those retired workflows, and next-action guidance
must follow the refusal reason.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from typing import Any

RETIRED_ACTION_IDS = (
    "prepare_deed_to_ir_final_package",
    "publish_deed_to_ir_output",
)
CANONICAL_FINALIZER_ACTION = "finalize_current_deed_to_ir_output"
SUBMIT_IR_FOR_MAPPING_ACTION = "submit_ir_for_mapping"

_TOOL_ACTION_IDS = frozenset(
    {
        CANONICAL_FINALIZER_ACTION,
        SUBMIT_IR_FOR_MAPPING_ACTION,
        *RETIRED_ACTION_IDS,
    }
)

_POST_PUBLICATION_COMPLETION_ACTIONS = frozenset({"complete_run"})

_STRIP_OUTPUT_KEYS = frozenset(
    {
        "finalization_decision_card",
        "retry_request_template",
        "retry_package_shell",
        "upstream_corrections_template",
        "correction_contract_card",
        "correction_contract_ref",
        "recommended_publish_request",
        "working_preview_ref",
        "preview_ready_summary",
    }
)

_ACTION_FIELD_KEYS = frozenset(
    {
        "expected_next",
        "next_required_action",
        "action_type",
        "action_id",
        "blocked_action_id",
    }
)

_REQUEST_IDENTITY_ACTION_KEYS = frozenset({"action_type", "action_id"})

_REPAIR_GUIDANCE_FIELDS = frozenset({"repair_hint", "next_repair_action"})

# Retryable decision / preview-publication failures → retry the finalizer.
_ROUTE_FINALIZE = frozenset(
    {
        "missing_finalization_decisions",
        "finalization_decision_invalid",
        "finalization_decision_unknown_id",
        "finalization_scope_dependency_conflict",
        "finalization_decisions_frozen",
        "finalization_session_persistence_failed",
        "publish_posture_audit_gate",
        # Recoverable internal publication interruptions (publisher may emit
        # retryable=false; boundary reclassifies before routing).
        "publication_in_progress",
        "final_pointer_write_failed",
    }
)

# Session / lineage / unusable stored-preview failures → remap first.
_ROUTE_REMAP = frozenset(
    {
        "finalization_session_missing",
        "finalization_session_stale",
        "finalization_session_invalid",
        "current_mapping_lineage_missing",
        "current_mapping_lineage_stale",
        "current_mapping_lineage_incomplete",
        "mapping_ir_lineage_mismatch",
        "final_package_preview_stale",
        "final_package_preview_revision_ref_missing",
        "final_package_preview_not_found",
        "final_package_preview_invalid",
        "final_package_preview_not_ready",
        "publish_payload_validation_failed",
        "final_package_incomplete",
        "final_package_preview_row_mutation_forbidden",
        "publish_request_ambiguous",
        "publish_target_required",
    }
)

# Publisher emits these via persistence_io.refusal (retryable=false). At the
# finalizer boundary they are canonically recoverable — reclassify before routing.
_RECLASSIFY_AS_RETRYABLE = frozenset(
    {
        "publication_in_progress",
        "final_pointer_write_failed",
        "final_package_preview_not_found",
        "final_package_preview_invalid",
        "final_package_preview_not_ready",
        "publish_payload_validation_failed",
        "final_package_incomplete",
        "final_package_preview_row_mutation_forbidden",
        "publish_request_ambiguous",
        "publish_target_required",
        "final_package_preview_stale",
        "final_package_preview_revision_ref_missing",
    }
)

_ROUTE_HITL = frozenset(
    {
        "finalization_requires_hitl",
    }
)

# Mirrors publish_gate_feedback posture classification prefixes.
_POSTURE_REASON_PREFIXES = (
    "work_universe_publish_",
    "work_universe_complete_",
    "closure_publish_",
    "closure_complete_",
    "missing_required_output_artifact:",
)

_CANONICAL_POSTURE_HINT = (
    "Patch readiness/audit posture if warranted, then retry "
    f"{CANONICAL_FINALIZER_ACTION} without decision mutations."
)

_CANONICAL_REMAP_HINT = (
    f"Submit the current IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
)

_CANONICAL_LINEAGE_MISMATCH_HINT = (
    f"Submit the expected IR for mapping, then retry {CANONICAL_FINALIZER_ACTION}."
)

_CANONICAL_FINALIZE_RETRY_HINT = (
    f"Retry {CANONICAL_FINALIZER_ACTION}. "
    "If the session is preview_ready, retry without decision mutations; "
    "otherwise supply only still-missing semantic decision IDs."
)

# Prose that teaches the retired prepare/publish workflow without naming tool IDs.
_RETIRED_WORKFLOW_PROSE_NEEDLES = (
    "prepare or publish",
    "prepare and publish",
    "retry publish",
    "retry prepare",
    "prepare a new final package preview",
    "same preview ref",
    "same final_package_preview_ref",
    "retry the same final_package_preview_ref",
    "publish with the same",
    "from a fresh preview",
    "prepare and publish from",
)


def route_finalizer_next_action(
    *,
    reason_code: str | None,
    retryable: bool,
) -> str | None:
    """Return the canonical next tool action, or None when none should be synthesized."""
    code = str(reason_code or "").strip()
    if not retryable or not code:
        return None
    if code in _ROUTE_HITL:
        return None
    if code in _ROUTE_FINALIZE or _is_posture_reason(code):
        return CANONICAL_FINALIZER_ACTION
    if code in _ROUTE_REMAP:
        return SUBMIT_IR_FOR_MAPPING_ACTION
    return None


def normalize_finalizer_agent_visible_result(result: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a sanitized copy safe for agent consumption."""
    if not isinstance(result, Mapping):
        return {"executed": False}
    sanitized = deepcopy(dict(result))
    reason_code, retryable = _extract_refusal_routing(sanitized)
    retryable = _reclassify_recoverable_publication_refusal(
        sanitized,
        reason_code=reason_code,
        retryable=retryable,
    )
    next_action = route_finalizer_next_action(reason_code=reason_code, retryable=retryable)

    _scrub_node(sanitized, reason_code=reason_code, next_action=next_action)

    outputs = sanitized.get("outputs")
    if isinstance(outputs, MutableMapping) and sanitized.get("executed") is True:
        _strip_post_publication_completion_routing(outputs)
    if isinstance(outputs, MutableMapping) and sanitized.get("executed") is False:
        _apply_top_level_next_action_routing(outputs, next_action=next_action)
    return sanitized


def _strip_post_publication_completion_routing(outputs: MutableMapping[str, Any]) -> None:
    status = str(outputs.get("finalization_status") or "").strip()
    summary = outputs.get("final_output_summary")
    ready = isinstance(summary, Mapping) and summary.get("ready_for_completion_candidate") is True
    if status != "published" and not ready:
        return
    for key in ("next_required_action", "expected_next"):
        if str(outputs.get(key) or "").strip() in _POST_PUBLICATION_COMPLETION_ACTIONS:
            outputs.pop(key, None)


def _reclassify_recoverable_publication_refusal(
    result: MutableMapping[str, Any],
    *,
    reason_code: str | None,
    retryable: bool,
) -> bool:
    """Flip canonically recoverable publisher refusals to retryable before routing.

    Internal ``publish_deed_to_ir_output`` uses ``persistence_io.refusal``
    (retryable=false, blocked_by_invariant=true) for several conditions that are
    recoverable from the compact finalizer session. Only explicitly listed codes
    are reclassified — other storage/invariant failures remain terminal.
    """
    code = str(reason_code or "").strip()
    if not code or code not in _RECLASSIFY_AS_RETRYABLE:
        return retryable
    refusal = result.get("refusal")
    if isinstance(refusal, MutableMapping):
        refusal["retryable"] = True
        refusal["blocked_by_invariant"] = False
    return True


def _is_posture_reason(reason_code: str | None) -> bool:
    code = str(reason_code or "").strip()
    if not code:
        return False
    if code == "publish_posture_audit_gate":
        return True
    return any(code.startswith(prefix) for prefix in _POSTURE_REASON_PREFIXES)


def _extract_refusal_routing(result: Mapping[str, Any]) -> tuple[str | None, bool]:
    refusal = result.get("refusal")
    if not isinstance(refusal, Mapping):
        return None, False
    reason_code = str(refusal.get("reason_code") or "").strip() or None
    if reason_code is None:
        outputs = result.get("outputs")
        if isinstance(outputs, Mapping):
            error = outputs.get("error")
            if isinstance(error, Mapping):
                reason_code = str(error.get("code") or "").strip() or None
            if reason_code is None:
                gate_code = str(outputs.get("publish_gate_reason_code") or "").strip()
                reason_code = gate_code or None
    retryable = bool(refusal.get("retryable"))
    return reason_code, retryable


def _apply_top_level_next_action_routing(
    outputs: MutableMapping[str, Any],
    *,
    next_action: str | None,
) -> None:
    """Authority for top-level outputs next-action fields only."""
    if next_action:
        outputs["next_required_action"] = next_action
        outputs["expected_next"] = next_action
        return
    for key in ("next_required_action", "expected_next"):
        value = outputs.get(key)
        if isinstance(value, str) and value.strip() in _TOOL_ACTION_IDS:
            outputs.pop(key, None)


def _scrub_node(
    node: Any,
    *,
    reason_code: str | None,
    next_action: str | None,
) -> None:
    if isinstance(node, MutableMapping):
        for key in list(node.keys()):
            if key in _STRIP_OUTPUT_KEYS:
                node.pop(key, None)
                continue
            value = node.get(key)
            if key in _ACTION_FIELD_KEYS and isinstance(value, str):
                _apply_action_field(
                    node,
                    key=str(key),
                    value=value,
                    next_action=next_action,
                )
                continue
            if isinstance(value, str):
                scrubbed = _scrub_string(
                    value,
                    field=str(key),
                    reason_code=reason_code,
                    next_action=next_action,
                )
                if scrubbed is None:
                    node.pop(key, None)
                else:
                    node[key] = scrubbed
            else:
                _scrub_node(value, reason_code=reason_code, next_action=next_action)
        return
    if isinstance(node, list):
        for index, value in enumerate(node):
            if isinstance(value, str):
                scrubbed = _scrub_string(
                    value,
                    reason_code=reason_code,
                    next_action=next_action,
                )
                node[index] = "" if scrubbed is None else scrubbed
            else:
                _scrub_node(value, reason_code=reason_code, next_action=next_action)


def _apply_action_field(
    node: MutableMapping[str, Any],
    *,
    key: str,
    value: str,
    next_action: str | None,
) -> None:
    text = value.strip()
    mentions_retired = any(rid in text for rid in RETIRED_ACTION_IDS)
    is_tool_valued = text in _TOOL_ACTION_IDS or mentions_retired

    if next_action is None:
        if text in _POST_PUBLICATION_COMPLETION_ACTIONS:
            node.pop(key, None)
            return
        if is_tool_valued:
            node.pop(key, None)
        return

    if not is_tool_valued:
        return

    if key in _REQUEST_IDENTITY_ACTION_KEYS:
        node.pop(key, None)
        return

    node[key] = next_action


def _scrub_string(
    text: str,
    *,
    field: str | None = None,
    reason_code: str | None = None,
    next_action: str | None = None,
) -> str | None:
    if field in _REPAIR_GUIDANCE_FIELDS:
        return _scrub_repair_hint(text, reason_code=reason_code, next_action=next_action)

    # Observability / diagnostic prose: strip retired tool IDs, but keep the message.
    if any(rid in text for rid in RETIRED_ACTION_IDS):
        cleaned = text
        for retired in RETIRED_ACTION_IDS:
            cleaned = cleaned.replace(
                retired,
                CANONICAL_FINALIZER_ACTION if next_action is not None else "",
            )
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" .,;:")
        return cleaned or None

    # Non-guidance fields that still teach prepare/publish workflow in prose.
    if _teaches_retired_workflow(text):
        if next_action == SUBMIT_IR_FOR_MAPPING_ACTION:
            return _canonical_remap_hint(reason_code)
        if next_action == CANONICAL_FINALIZER_ACTION and _is_posture_reason(reason_code):
            return _CANONICAL_POSTURE_HINT
        if next_action == CANONICAL_FINALIZER_ACTION:
            return _CANONICAL_FINALIZE_RETRY_HINT
        # Unknown / HITL / non-retryable: drop workflow-teaching fragments only when
        # this is not a repair field (handled above). Leave unrelated diagnostics.
        return text
    return text


def _scrub_repair_hint(
    text: str,
    *,
    reason_code: str | None,
    next_action: str | None,
) -> str | None:
    """Normalize repair guidance by reason first; never leave prepare/publish prose."""
    # Reason-specific canonical hints apply before any retired-ID / prose checks.
    if next_action == SUBMIT_IR_FOR_MAPPING_ACTION:
        return _canonical_remap_hint(reason_code)
    if next_action == CANONICAL_FINALIZER_ACTION and _is_posture_reason(reason_code):
        return _CANONICAL_POSTURE_HINT
    if next_action == CANONICAL_FINALIZER_ACTION:
        if _teaches_retired_workflow(text):
            return _CANONICAL_FINALIZE_RETRY_HINT
        return text

    # HITL / non-retryable / unknown: omit workflow-teaching hints entirely.
    if _teaches_retired_workflow(text):
        return None
    cleaned = text.strip()
    return cleaned or None


def _canonical_remap_hint(reason_code: str | None) -> str:
    if str(reason_code or "").strip() == "mapping_ir_lineage_mismatch":
        return _CANONICAL_LINEAGE_MISMATCH_HINT
    return _CANONICAL_REMAP_HINT


def _teaches_retired_workflow(text: str) -> bool:
    """True when text names retired tool IDs or teaches prepare/publish workflow in prose."""
    if any(rid in text for rid in RETIRED_ACTION_IDS):
        return True
    lower = text.lower()
    if any(needle in lower for needle in _RETIRED_WORKFLOW_PROSE_NEEDLES):
        return True
    if "prepare" in lower and "preview" in lower:
        return True
    if re.search(r"\bpublish\b", lower) and (
        "preview" in lower or "final_package" in lower
    ):
        return True
    return False
