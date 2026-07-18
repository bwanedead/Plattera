"""Inert pending-result delivery substrate (mechanical only).

Owns admission, bounded retention, supersession, pure projection, and contact
acknowledgement for recent action results. Does not attach to production prompts
or interpret domain schemas / continuity-key prefixes.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Mapping

from harness.execution.agent_result_view import (
    MAX_AGENT_RESULT_VIEW_CHARS,
    MAX_CONTINUITY_KEY_CHARS,
    OMISSION_REASON_INVALID_SHAPE,
    OMISSION_REASON_NOT_JSON_SAFE,
    OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION,
    OMISSION_REASON_VIEW_BUDGET,
    AgentResultView,
    agent_result_view_omission_from_wire,
    agent_result_view_omission_to_wire,
    agent_result_view_to_wire,
    normalize_agent_result_view_pair,
)
from harness.execution.contracts import ActionDispatchResult
from harness.execution.wire_codec import execution_refusal_from_wire, execution_refusal_to_wire

PENDING_RESULT_DELIVERY_SCHEMA_VERSION = "pending_result_delivery.v1"

MIN_REQUIRED_RESULT_CONTACTS = 2
MAX_RESULT_CONTACTS = 8
MAX_PENDING_RESULT_DELIVERIES = 32
MAX_LATEST_ACTION_RESULTS_CHARS = 64_000
MAX_DELIVERY_ARTIFACT_REFS = 32
MAX_DELIVERY_ARTIFACT_REF_CHARS = 512
MAX_DELIVERY_OUTPUT_KEYS = 32
MAX_DELIVERY_ID_CHARS = 256
MAX_ACTION_ALIAS_CHARS = 128
MAX_ACTION_ID_CHARS = 128
MAX_EXECUTION_STATE_CHARS = 64
MAX_REASON_CODES = 16
MAX_REASON_CODE_CHARS = 128
MAX_CONTACT_ID_CHARS = 128
MAX_REFUSAL_REASON_CHARS = 256
MAX_REFUSAL_MISSING_INPUTS = 16
MAX_OUTPUT_KEY_CHARS = 128
MAX_SOURCE_TURN_INDEX = 1_000_000_000
MAX_ACTION_INDEX = 1_000_000_000

REPRESENTATION_EXACT_OUTPUTS = "exact_outputs"
REPRESENTATION_AGENT_RESULT_VIEW = "agent_result_view"
REPRESENTATION_UNAVAILABLE = "unavailable"

REASON_MISSING_VIEW = "missing_agent_result_view"
REASON_INVALID_VIEW = "invalid_agent_result_view"
REASON_LANE_BUDGET = "lane_budget"
REASON_LANE_BUDGET_AGGREGATE = "lane_budget_aggregate"
REASON_CAPACITY_EXCEEDED = "pending_result_delivery_capacity_exceeded"
REASON_INVALID_ROW = "pending_result_delivery_invalid_row"

_ALLOWED_OMISSION_REASONS = frozenset(
    {
        OMISSION_REASON_INVALID_SHAPE,
        OMISSION_REASON_UNSUPPORTED_SCHEMA_VERSION,
        OMISSION_REASON_NOT_JSON_SAFE,
        OMISSION_REASON_VIEW_BUDGET,
    }
)
_ALLOWED_REPRESENTATION_KINDS = frozenset(
    {
        REPRESENTATION_EXACT_OUTPUTS,
        REPRESENTATION_AGENT_RESULT_VIEW,
        REPRESENTATION_UNAVAILABLE,
    }
)
_ALLOWED_STORED_KEYS = frozenset(
    {
        "schema_version",
        "delivery_id",
        "source_turn_index",
        "action_index",
        "action_alias",
        "action_id",
        "execution_state",
        "executed",
        "reason_codes",
        "reason_codes_omitted_count",
        "refusal",
        "artifact_refs",
        "artifact_refs_omitted_count",
        "representation_kind",
        "representation",
        "continuity_key",
        "successful_content_contact_ids",
        "view_omission_reason",
    }
)
_ALLOWED_UNAVAILABLE_KEYS = frozenset(
    {
        "reason",
        "observed_output_chars",
        "maximum_content_chars",
        "output_keys",
        "output_keys_omitted_count",
        "view_omission",
    }
)
_ALLOWED_REFUSAL_KEYS = frozenset(
    {
        "reason_code",
        "retryable",
        "blocked_by_budget",
        "blocked_by_invariant",
        "missing_inputs",
    }
)


@dataclass(frozen=True)
class AdmissionOutcome:
    status: str
    delivery_id: str | None = None
    reason_code: str | None = None


@dataclass(frozen=True)
class ContactReceipt:
    """What the renderer actually exposed (content vs temporary lane-budget)."""

    content_exposed_delivery_ids: tuple[str, ...] = ()
    lane_budget_delivery_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultDeliveryProjection:
    latest_action_results: list[dict[str, Any]]
    contact_receipt: ContactReceipt
    serialized_chars: int


def make_delivery_id(*, source_turn_index: int, action_index: int, action_alias: str) -> str:
    alias = str(action_alias or "").strip() or "action"
    return f"turn:{int(source_turn_index)}:action:{int(action_index)}:{alias}"


def measure_compact_json_chars(value: Any) -> int:
    return len(
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def contact_count(row: Mapping[str, Any]) -> int:
    ids = row.get("successful_content_contact_ids")
    if not isinstance(ids, list):
        return 0
    return len(ids)


def admit_pending_result_delivery(
    deliveries: list[dict[str, Any]],
    *,
    result: ActionDispatchResult,
    source_turn_index: int,
    action_index: int,
    action_alias: str,
    execution_state: str,
) -> AdmissionOutcome:
    """Admit one dispatch result into pending delivery state (mutates ``deliveries``).

    Existing rows are left byte-for-byte unchanged when admission is rejected.
    """
    delivery_id = make_delivery_id(
        source_turn_index=source_turn_index,
        action_index=action_index,
        action_alias=action_alias,
    )
    for existing in deliveries:
        if str(existing.get("delivery_id") or "") == delivery_id:
            return AdmissionOutcome(status="idempotent", delivery_id=delivery_id)

    row = _build_delivery_row(
        result=result,
        source_turn_index=source_turn_index,
        action_index=action_index,
        action_alias=action_alias,
        execution_state=execution_state,
        delivery_id=delivery_id,
    )
    validated = validate_stored_pending_result_delivery(row)
    if validated is None:
        return AdmissionOutcome(
            status="rejected",
            delivery_id=delivery_id,
            reason_code=REASON_INVALID_ROW,
        )

    candidate = list(deliveries)
    continuity_key = validated.get("continuity_key")
    if isinstance(continuity_key, str) and continuity_key:
        candidate = [
            item
            for item in candidate
            if not (
                isinstance(item.get("continuity_key"), str)
                and str(item.get("continuity_key")) == continuity_key
            )
        ]
    _make_capacity_for_admission(candidate)
    if len(candidate) >= MAX_PENDING_RESULT_DELIVERIES:
        return AdmissionOutcome(
            status="rejected",
            delivery_id=delivery_id,
            reason_code=REASON_CAPACITY_EXCEEDED,
        )

    candidate.append(validated)
    deliveries[:] = candidate
    return AdmissionOutcome(status="admitted", delivery_id=delivery_id)


def project_latest_action_results(
    pending_result_deliveries: list[dict[str, Any]] | tuple[dict[str, Any], ...],
) -> ResultDeliveryProjection:
    """Pure renderer: never mutates continuity state.

    Always guarantees ``serialized_chars <= MAX_LATEST_ACTION_RESULTS_CHARS``.
    """
    rows = [dict(item) for item in pending_result_deliveries]
    if not rows:
        empty_chars = measure_compact_json_chars([])
        return ResultDeliveryProjection(
            latest_action_results=[],
            contact_receipt=ContactReceipt(),
            serialized_chars=empty_chars,
        )

    detailed = [_project_detailed_row(item) for item in rows]
    full_chars = measure_compact_json_chars(detailed)
    if full_chars <= MAX_LATEST_ACTION_RESULTS_CHARS:
        return ResultDeliveryProjection(
            latest_action_results=detailed,
            contact_receipt=ContactReceipt(
                content_exposed_delivery_ids=tuple(str(r["delivery_id"]) for r in detailed),
            ),
            serialized_chars=full_chars,
        )

    minimal = [_project_lane_budget_row(item) for item in rows]
    minimal_chars = measure_compact_json_chars(minimal)
    if minimal_chars > MAX_LATEST_ACTION_RESULTS_CHARS:
        # Defensive fallback for corrupt/noncanonical input only.
        aggregate = _project_aggregate_lane_budget(len(rows), observed_chars=minimal_chars)
        return ResultDeliveryProjection(
            latest_action_results=[aggregate],
            contact_receipt=ContactReceipt(),
            serialized_chars=measure_compact_json_chars([aggregate]),
        )

    priority = sorted(
        range(len(rows)),
        key=lambda i: (
            contact_count(rows[i]),
            int(rows[i].get("source_turn_index") or 0),
            int(rows[i].get("action_index") or 0),
            str(rows[i].get("delivery_id") or ""),
        ),
    )

    projected = list(minimal)
    content_ids: list[str] = []
    lane_ids = [str(r["delivery_id"]) for r in minimal]

    for idx in priority:
        candidate = list(projected)
        candidate[idx] = detailed[idx]
        chars = measure_compact_json_chars(candidate)
        if chars <= MAX_LATEST_ACTION_RESULTS_CHARS:
            projected = candidate
            did = str(detailed[idx]["delivery_id"])
            if did not in content_ids:
                content_ids.append(did)
            if did in lane_ids:
                lane_ids = [x for x in lane_ids if x != did]

    return ResultDeliveryProjection(
        latest_action_results=projected,
        contact_receipt=ContactReceipt(
            content_exposed_delivery_ids=tuple(content_ids),
            lane_budget_delivery_ids=tuple(lane_ids),
        ),
        serialized_chars=measure_compact_json_chars(projected),
    )


def acknowledge_result_delivery_contacts(
    deliveries: list[dict[str, Any]],
    *,
    contact_id: str,
    receipt: ContactReceipt,
    active_attention_refs: Mapping[str, Any] | set[str] | frozenset[str] | list[str] | tuple[str, ...] | None = None,
) -> None:
    """Apply one mechanical prompt-contact acknowledgement (mutates ``deliveries``)."""
    cid = str(contact_id or "").strip()
    if not cid or len(cid) > MAX_CONTACT_ID_CHARS:
        return
    active = _normalize_active_refs(active_attention_refs)
    content_ids = {str(x) for x in receipt.content_exposed_delivery_ids}

    retained: list[dict[str, Any]] = []
    for row in deliveries:
        did = str(row.get("delivery_id") or "")
        item = dict(row)
        ids = list(item.get("successful_content_contact_ids") or [])
        if did in content_ids and cid not in ids and len(ids) < MAX_RESULT_CONTACTS:
            ids.append(cid)
            item["successful_content_contact_ids"] = ids
        contacts = len(item.get("successful_content_contact_ids") or [])
        if contacts < MIN_REQUIRED_RESULT_CONTACTS:
            retained.append(item)
            continue
        if contacts >= MAX_RESULT_CONTACTS:
            continue
        refs = [
            r
            for r in list(item.get("artifact_refs") or [])
            if isinstance(r, str) and r
        ]
        if any(ref in active for ref in refs):
            retained.append(item)
            continue
    deliveries[:] = retained


def validate_stored_pending_result_delivery(row: Any) -> dict[str, Any] | None:
    """Resume/admission validator. Rejects malformed rows; does not repair."""
    if not isinstance(row, Mapping):
        return None
    if any(key not in _ALLOWED_STORED_KEYS for key in row.keys()):
        return None
    if row.get("schema_version") != PENDING_RESULT_DELIVERY_SCHEMA_VERSION:
        return None

    delivery_id = row.get("delivery_id")
    if not _bounded_nonblank_str(delivery_id, MAX_DELIVERY_ID_CHARS):
        return None
    source_turn_index = _strict_bounded_index(row.get("source_turn_index"), MAX_SOURCE_TURN_INDEX)
    action_index = _strict_bounded_index(row.get("action_index"), MAX_ACTION_INDEX)
    if source_turn_index is None or action_index is None:
        return None

    action_alias = row.get("action_alias")
    action_id = row.get("action_id")
    execution_state = row.get("execution_state")
    if not _bounded_nonblank_str(action_alias, MAX_ACTION_ALIAS_CHARS):
        return None
    if not _bounded_nonblank_str(action_id, MAX_ACTION_ID_CHARS):
        return None
    if not _bounded_nonblank_str(execution_state, MAX_EXECUTION_STATE_CHARS):
        return None
    if type(row.get("executed")) is not bool:
        return None

    expected_id = make_delivery_id(
        source_turn_index=source_turn_index,
        action_index=action_index,
        action_alias=action_alias,
    )
    if delivery_id != expected_id:
        return None

    reason_codes = _validate_reason_codes(row.get("reason_codes"))
    if reason_codes is None:
        return None
    omitted_reason_codes = _strict_nonneg_int(row.get("reason_codes_omitted_count"))
    if omitted_reason_codes is None:
        return None
    refusal = _validate_refusal(row.get("refusal"))
    if refusal is False:
        return None

    refs = _validate_canonical_artifact_refs(row.get("artifact_refs"))
    if refs is None:
        return None
    omitted_refs = _strict_nonneg_int(row.get("artifact_refs_omitted_count"))
    if omitted_refs is None:
        return None

    kind = row.get("representation_kind")
    if kind not in _ALLOWED_REPRESENTATION_KINDS:
        return None
    representation = _validate_representation(kind, row.get("representation"))
    if representation is None:
        return None

    continuity_key = row.get("continuity_key")
    if continuity_key is not None:
        if not _bounded_nonblank_str(continuity_key, MAX_CONTINUITY_KEY_CHARS):
            return None

    contact_ids = _validate_contact_ids(row.get("successful_content_contact_ids"))
    if contact_ids is None:
        return None

    view_omission = row.get("view_omission_reason")
    if view_omission is not None:
        if view_omission not in _ALLOWED_OMISSION_REASONS:
            return None

    if not _representation_continuity_consistent(
        kind=kind,
        representation=representation,
        continuity_key=continuity_key,
        view_omission_reason=view_omission,
    ):
        return None

    out: dict[str, Any] = {
        "schema_version": PENDING_RESULT_DELIVERY_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "source_turn_index": source_turn_index,
        "action_index": action_index,
        "action_alias": action_alias,
        "action_id": action_id,
        "execution_state": execution_state,
        "executed": row.get("executed"),
        "reason_codes": reason_codes,
        "reason_codes_omitted_count": omitted_reason_codes,
        "refusal": refusal,
        "artifact_refs": refs,
        "artifact_refs_omitted_count": omitted_refs,
        "representation_kind": kind,
        "representation": representation,
        "continuity_key": continuity_key,
        "successful_content_contact_ids": contact_ids,
    }
    if view_omission is not None:
        out["view_omission_reason"] = view_omission
    return out


def _build_delivery_row(
    *,
    result: ActionDispatchResult,
    source_turn_index: int,
    action_index: int,
    action_alias: str,
    execution_state: str,
    delivery_id: str,
) -> dict[str, Any]:
    outputs = dict(result.outputs) if isinstance(result.outputs, dict) else {}
    view, view_omission = normalize_agent_result_view_pair(
        result.agent_result_view,
        result.agent_result_view_omitted,
    )
    continuity_key = view.continuity_key if view is not None else None
    view_omission_reason = view_omission.reason if view_omission is not None else None

    representation_kind, representation = _select_representation(
        outputs=outputs,
        view=view,
        view_omission=view_omission,
    )
    refs, omitted_refs = _bound_artifact_refs(result.artifact_refs)
    refusal = execution_refusal_to_wire(result.refusal) if result.refusal is not None else None

    alias = str(action_alias or "").strip() or "action"
    state = str(execution_state or "").strip() or "executed"
    action_id = str(result.action_id or "").strip() or "action"
    reason_codes, omitted_reason_codes = _bound_reason_codes(result.reason_codes)

    row: dict[str, Any] = {
        "schema_version": PENDING_RESULT_DELIVERY_SCHEMA_VERSION,
        "delivery_id": delivery_id,
        "source_turn_index": int(source_turn_index),
        "action_index": int(action_index),
        "action_alias": alias,
        "action_id": action_id,
        "execution_state": state,
        "executed": bool(result.executed),
        "reason_codes": reason_codes,
        "reason_codes_omitted_count": omitted_reason_codes,
        "refusal": refusal,
        "artifact_refs": refs,
        "artifact_refs_omitted_count": omitted_refs,
        "representation_kind": representation_kind,
        "representation": representation,
        "continuity_key": continuity_key,
        "successful_content_contact_ids": [],
    }
    if view_omission_reason is not None:
        row["view_omission_reason"] = view_omission_reason
    return row


def _select_representation(
    *,
    outputs: dict[str, Any],
    view: AgentResultView | None,
    view_omission: Any,
) -> tuple[str, dict[str, Any]]:
    exact_ok = _is_json_safe(outputs)
    if exact_ok:
        try:
            output_chars = measure_compact_json_chars(outputs)
        except (TypeError, ValueError):
            exact_ok = False
            output_chars = MAX_AGENT_RESULT_VIEW_CHARS + 1
    else:
        output_chars = MAX_AGENT_RESULT_VIEW_CHARS + 1

    if exact_ok and output_chars <= MAX_AGENT_RESULT_VIEW_CHARS:
        return REPRESENTATION_EXACT_OUTPUTS, dict(outputs)

    if view is not None:
        return REPRESENTATION_AGENT_RESULT_VIEW, agent_result_view_to_wire(view)

    reason = REASON_INVALID_VIEW if view_omission is not None else REASON_MISSING_VIEW
    keys: list[str] = []
    omitted_key_count = 0
    candidates: list[str] = []
    for raw_key in outputs.keys():
        if not isinstance(raw_key, str):
            omitted_key_count += 1
            continue
        key = raw_key.strip()
        if not key or len(key) > MAX_OUTPUT_KEY_CHARS:
            omitted_key_count += 1
            continue
        candidates.append(key)
    candidates.sort()
    keys = candidates[:MAX_DELIVERY_OUTPUT_KEYS]
    omitted_key_count += max(0, len(candidates) - len(keys))
    marker: dict[str, Any] = {
        "reason": reason,
        "observed_output_chars": int(output_chars),
        "maximum_content_chars": MAX_AGENT_RESULT_VIEW_CHARS,
        "output_keys": keys,
        "output_keys_omitted_count": omitted_key_count,
    }
    if view_omission is not None:
        marker["view_omission"] = agent_result_view_omission_to_wire(view_omission)
    return REPRESENTATION_UNAVAILABLE, marker


def _validate_representation(kind: str, representation: Any) -> dict[str, Any] | None:
    if not isinstance(representation, dict):
        return None
    if kind == REPRESENTATION_EXACT_OUTPUTS:
        if not _is_json_safe(representation):
            return None
        try:
            if measure_compact_json_chars(representation) > MAX_AGENT_RESULT_VIEW_CHARS:
                return None
        except (TypeError, ValueError):
            return None
        return dict(representation)
    if kind == REPRESENTATION_AGENT_RESULT_VIEW:
        view, omitted = normalize_agent_result_view_pair(representation, None)
        if view is None or omitted is not None:
            return None
        return agent_result_view_to_wire(view)
    if kind == REPRESENTATION_UNAVAILABLE:
        if any(key not in _ALLOWED_UNAVAILABLE_KEYS for key in representation.keys()):
            return None
        reason = representation.get("reason")
        if reason == REASON_LANE_BUDGET:
            if set(representation.keys()) != {"reason"}:
                return None
            return {"reason": REASON_LANE_BUDGET}
        if reason not in {REASON_MISSING_VIEW, REASON_INVALID_VIEW}:
            return None
        observed = _strict_nonneg_int(representation.get("observed_output_chars"))
        maximum = _strict_nonneg_int(representation.get("maximum_content_chars"))
        omitted_keys = _strict_nonneg_int(representation.get("output_keys_omitted_count"))
        if observed is None or maximum is None or omitted_keys is None:
            return None
        if maximum != MAX_AGENT_RESULT_VIEW_CHARS:
            return None
        keys_raw = representation.get("output_keys")
        if not isinstance(keys_raw, list) or len(keys_raw) > MAX_DELIVERY_OUTPUT_KEYS:
            return None
        keys: list[str] = []
        for key in keys_raw:
            if not _bounded_nonblank_str(key, MAX_OUTPUT_KEY_CHARS):
                return None
            keys.append(key)
        out: dict[str, Any] = {
            "reason": reason,
            "observed_output_chars": observed,
            "maximum_content_chars": maximum,
            "output_keys": keys,
            "output_keys_omitted_count": omitted_keys,
        }
        if "view_omission" in representation:
            if reason != REASON_INVALID_VIEW:
                return None
            omission = agent_result_view_omission_from_wire(representation.get("view_omission"))
            if omission is None:
                return None
            out["view_omission"] = agent_result_view_omission_to_wire(omission)
        elif reason == REASON_INVALID_VIEW:
            return None
        return out
    return None


def _representation_continuity_consistent(
    *,
    kind: str,
    representation: Mapping[str, Any],
    continuity_key: str | None,
    view_omission_reason: str | None,
) -> bool:
    if kind == REPRESENTATION_AGENT_RESULT_VIEW:
        if view_omission_reason is not None:
            return False
        envelope_key = representation.get("continuity_key")
        if envelope_key is None:
            return continuity_key is None
        return continuity_key == envelope_key
    if kind == REPRESENTATION_UNAVAILABLE:
        reason = representation.get("reason")
        if reason == REASON_MISSING_VIEW:
            return (
                continuity_key is None
                and view_omission_reason is None
                and "view_omission" not in representation
            )
        if reason == REASON_INVALID_VIEW:
            if continuity_key is not None:
                return False
            nested = representation.get("view_omission")
            if not isinstance(nested, Mapping):
                return False
            return view_omission_reason is not None and view_omission_reason == nested.get("reason")
        # Projected lane-budget markers are not stored; reject if somehow persisted.
        return False
    if kind == REPRESENTATION_EXACT_OUTPUTS:
        if continuity_key is not None and view_omission_reason is not None:
            return False
        return True
    return False


def _project_detailed_row(row: Mapping[str, Any]) -> dict[str, Any]:
    kind = row.get("representation_kind")
    representation = dict(row.get("representation") or {})
    if kind == REPRESENTATION_AGENT_RESULT_VIEW:
        # Opaque continuity_key stays internal; agent projection is schema+payload only.
        payload = representation.get("payload")
        representation = {
            "schema_version": representation.get("schema_version"),
            "schema_id": representation.get("schema_id"),
            "payload": dict(payload) if isinstance(payload, dict) else {},
        }
    identity = _project_identity_fields(row)
    reason_codes = [
        code
        for code in list(row.get("reason_codes") or [])[:MAX_REASON_CODES]
        if isinstance(code, str) and code
    ]
    refs = [
        ref
        for ref in list(row.get("artifact_refs") or [])[:MAX_DELIVERY_ARTIFACT_REFS]
        if isinstance(ref, str) and ref and len(ref) <= MAX_DELIVERY_ARTIFACT_REF_CHARS
    ]
    omitted = _project_index_or_zero(row.get("artifact_refs_omitted_count"), maximum=10**12)
    omitted_reasons = _project_index_or_zero(row.get("reason_codes_omitted_count"), maximum=10**12)
    refusal = None
    raw_refusal = row.get("refusal")
    if isinstance(raw_refusal, dict):
        refusal = dict(raw_refusal)
    return {
        **identity,
        "reason_codes": reason_codes,
        "reason_codes_omitted_count": omitted_reasons,
        "refusal": refusal,
        "artifact_refs": refs,
        "artifact_refs_omitted_count": omitted,
        "representation_kind": kind
        if kind in _ALLOWED_REPRESENTATION_KINDS
        else REPRESENTATION_UNAVAILABLE,
        "representation": representation
        if isinstance(representation, dict)
        else {"reason": REASON_LANE_BUDGET},
    }


def _project_lane_budget_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Genuinely minimal lane-pressure row: identity + counts, no bulky lists."""
    stored_refs = [
        r
        for r in list(row.get("artifact_refs") or [])
        if isinstance(r, str) and r and len(r) <= MAX_DELIVERY_ARTIFACT_REF_CHARS
    ]
    stored_omitted = _project_index_or_zero(row.get("artifact_refs_omitted_count"), maximum=10**12)
    omitted_reasons = _project_index_or_zero(row.get("reason_codes_omitted_count"), maximum=10**12)
    return {
        **_project_identity_fields(row),
        "representation_kind": REPRESENTATION_UNAVAILABLE,
        "representation": {"reason": REASON_LANE_BUDGET},
        # Suppression of stored refs is explicit via omitted count (not empty+zero).
        "artifact_refs": [],
        "artifact_refs_omitted_count": stored_omitted + len(stored_refs),
        "reason_codes_omitted_count": omitted_reasons,
    }


def _project_identity_fields(row: Mapping[str, Any]) -> dict[str, Any]:
    """Identity/posture fields for projection.

    Values accepted by the stored-row validator are projected unchanged.
    Overlong corrupt strings are left intact so the collection may fall through to
    the aggregate diagnostic rather than fabricating truncated identifiers.
    """
    return {
        "delivery_id": _proj_str(row.get("delivery_id"), fallback="unknown"),
        "source_turn_index": _project_accepted_index(
            row.get("source_turn_index"), maximum=MAX_SOURCE_TURN_INDEX
        ),
        "action_index": _project_accepted_index(row.get("action_index"), maximum=MAX_ACTION_INDEX),
        "action_alias": _proj_str(row.get("action_alias"), fallback="action"),
        "action_id": _proj_str(row.get("action_id"), fallback="action"),
        "execution_state": _proj_str(row.get("execution_state"), fallback="executed"),
        "executed": bool(row.get("executed")) if type(row.get("executed")) is bool else False,
    }


def _proj_str(value: Any, *, fallback: str) -> str:
    if not isinstance(value, str) or not value:
        return fallback
    return value


def _project_accepted_index(value: Any, *, maximum: int) -> int:
    """Pass through validator-accepted indices; coerce only corrupt values."""
    if type(value) is int and 0 <= value <= maximum:
        return value
    return 0


def _project_index_or_zero(value: Any, *, maximum: int) -> int:
    if type(value) is int and 0 <= value <= maximum:
        return value
    return 0


def _project_aggregate_lane_budget(pending_count: int, *, observed_chars: int) -> dict[str, Any]:
    return {
        "representation_kind": REPRESENTATION_UNAVAILABLE,
        "representation": {
            "reason": REASON_LANE_BUDGET_AGGREGATE,
            "pending_count": int(pending_count),
            "observed_chars": int(observed_chars),
            "maximum_chars": MAX_LATEST_ACTION_RESULTS_CHARS,
        },
    }


def _make_capacity_for_admission(deliveries: list[dict[str, Any]]) -> None:
    if len(deliveries) < MAX_PENDING_RESULT_DELIVERIES:
        return
    deliveries[:] = [item for item in deliveries if contact_count(item) < MAX_RESULT_CONTACTS]
    if len(deliveries) < MAX_PENDING_RESULT_DELIVERIES:
        return
    while len(deliveries) >= MAX_PENDING_RESULT_DELIVERIES:
        evict_idx = None
        for i, item in enumerate(deliveries):
            if contact_count(item) >= MIN_REQUIRED_RESULT_CONTACTS:
                evict_idx = i
                break
        if evict_idx is None:
            break
        deliveries.pop(evict_idx)


def _bound_artifact_refs(raw: Any) -> tuple[list[str], int]:
    """Admission-time ref binding: omit invalid/overlong refs whole (never truncate)."""
    seen: set[str] = set()
    out: list[str] = []
    omitted = 0
    source = list(raw or []) if isinstance(raw, (list, tuple)) else []
    for item in source:
        if not isinstance(item, str):
            omitted += 1
            continue
        text = item.strip()
        if not text or len(text) > MAX_DELIVERY_ARTIFACT_REF_CHARS:
            omitted += 1
            continue
        if text in seen:
            continue
        seen.add(text)
        if len(out) >= MAX_DELIVERY_ARTIFACT_REFS:
            omitted += 1
            continue
        out.append(text)
    return out, omitted


def _validate_canonical_artifact_refs(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    if len(raw) > MAX_DELIVERY_ARTIFACT_REFS:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not isinstance(item, str):
            return None
        if not item or item.strip() != item:
            return None
        if len(item) > MAX_DELIVERY_ARTIFACT_REF_CHARS:
            return None
        if item in seen:
            return None
        seen.add(item)
        out.append(item)
    return out


def _bound_reason_codes(raw: Any) -> tuple[list[str], int]:
    """Admission-time reason-code binding: omit invalid/overlong/excess whole."""
    out: list[str] = []
    omitted = 0
    source = list(raw or []) if isinstance(raw, (list, tuple)) else []
    for item in source:
        if not isinstance(item, str):
            omitted += 1
            continue
        text = item.strip()
        if not text or len(text) > MAX_REASON_CODE_CHARS:
            omitted += 1
            continue
        if len(out) >= MAX_REASON_CODES:
            omitted += 1
            continue
        out.append(text)
    return out, omitted


def _validate_contact_ids(raw: Any) -> list[str] | None:
    if raw is None:
        return []
    if not isinstance(raw, list):
        return None
    if len(raw) > MAX_RESULT_CONTACTS:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for item in raw:
        if not _bounded_nonblank_str(item, MAX_CONTACT_ID_CHARS):
            return None
        if item in seen:
            return None
        seen.add(item)
        out.append(item)
    return out


def _validate_reason_codes(raw: Any) -> list[str] | None:
    if not isinstance(raw, list):
        return None
    if len(raw) > MAX_REASON_CODES:
        return None
    out: list[str] = []
    for item in raw:
        if not _bounded_nonblank_str(item, MAX_REASON_CODE_CHARS):
            return None
        out.append(item)
    return out


def _validate_refusal(raw: Any) -> dict[str, Any] | None | bool:
    """Return refusal dict, None if absent, or False if invalid.

    Raw wire types are checked before decoding so coercible-but-noncanonical
    forms (e.g. ``\"false\"``, string ``missing_inputs``) are rejected.
    """
    if raw is None:
        return None
    if not isinstance(raw, Mapping):
        return False
    if any(key not in _ALLOWED_REFUSAL_KEYS for key in raw.keys()):
        return False
    reason_code = raw.get("reason_code")
    if not _bounded_nonblank_str(reason_code, MAX_REFUSAL_REASON_CHARS):
        return False
    for flag in ("retryable", "blocked_by_budget", "blocked_by_invariant"):
        if type(raw.get(flag)) is not bool:
            return False
    missing_raw = raw.get("missing_inputs")
    if not isinstance(missing_raw, list):
        return False
    if len(missing_raw) > MAX_REFUSAL_MISSING_INPUTS:
        return False
    for item in missing_raw:
        if not _bounded_nonblank_str(item, MAX_REASON_CODE_CHARS):
            return False
    parsed = execution_refusal_from_wire(raw)
    if parsed is None:
        return False
    return execution_refusal_to_wire(parsed)


def _normalize_active_refs(
    active_attention_refs: Mapping[str, Any] | set[str] | frozenset[str] | list[str] | tuple[str, ...] | None,
) -> set[str]:
    if active_attention_refs is None:
        return set()
    if isinstance(active_attention_refs, Mapping):
        values = list(active_attention_refs.values()) + list(active_attention_refs.keys())
    else:
        values = list(active_attention_refs)
    out: set[str] = set()
    for item in values:
        if isinstance(item, str) and item.strip():
            out.add(item.strip())
    return out


def _bounded_nonblank_str(value: Any, maximum: int) -> bool:
    return isinstance(value, str) and bool(value) and value.strip() == value and len(value) <= maximum


def _strict_nonneg_int(value: Any) -> int | None:
    if type(value) is not int:
        return None
    if value < 0:
        return None
    return value


def _strict_bounded_index(value: Any, maximum: int) -> int | None:
    parsed = _strict_nonneg_int(value)
    if parsed is None or parsed > maximum:
        return None
    return parsed


def _is_json_safe(value: Any) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(isinstance(k, str) and _is_json_safe(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_is_json_safe(item) for item in value)
    return False
