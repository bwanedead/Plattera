"""Strict request validation for apply_transcript_edits (tooling-owned)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    ALLOWED_DETERMINATIONS,
    ALLOWED_UNCERTAINTY_REASONS,
    DETERMINATION_EARNED,
    DETERMINATION_PROVISIONAL,
    MAX_CANDIDATE_VALUES_PER_DECISION,
    MAX_CONTEXT_TEXT_CHARS,
    MAX_DECISION_ID_CHARS,
    MAX_DECISIONS_PER_REQUEST,
    MAX_EDIT_TEXT_CHARS,
    MAX_EDITS_PER_DECISION,
    MAX_EVIDENCE_REFS_PER_DECISION,
    MAX_REQUEST_SERIALIZED_CHARS,
    MAX_UNCERTAINTY_REASONS_PER_DECISION,
    MAX_VERIFICATION_BASIS_CHARS,
    TRANSCRIPT_EDIT_LANES,
)


class ApplyTranscriptEditsContractError(Exception):
    """Whole-request refusal while validating apply_transcript_edits inputs."""

    def __init__(
        self,
        reason_code: str,
        detail: str = "",
        *,
        repair_hint: str | None = None,
    ) -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail or "")
        if type(repair_hint) is str:
            stripped = repair_hint.strip()
            self.repair_hint = stripped or None
        else:
            self.repair_hint = None
        message = self.reason_code if not self.detail else f"{self.reason_code}: {self.detail}"
        super().__init__(message)


# Stable, bounded repair vocabulary — no request body or source text.
_EDIT_ROW_FIELD_KEYS = frozenset({"lane", "expected_text", "replacement_text"})
_NESTING_REPAIR_HINT = (
    "Move lane, expected_text, and replacement_text into a decision's nonempty "
    "edits[] rows. Keep determination, uncertainty reasons, verification basis, "
    "and evidence refs on the decision."
)
_UNKNOWN_DECISION_FIELD_REPAIR_HINT = (
    "Remove unknown decision fields. Allowed decision fields: decision_id, "
    "determination, uncertainty_reasons, verification_basis, candidate_values, "
    "evidence_refs, edits."
)
_REPAIR_HINTS_BY_REASON: dict[str, str] = {
    "decision_id_required": "Provide a nonblank decision_id on the decision.",
    "verification_basis_required": (
        "Provide a nonblank verification_basis on the decision."
    ),
    "uncertainty_reasons_required": (
        "Provide uncertainty_reasons as a list on the decision "
        "(nonempty for provisional; empty list for earned)."
    ),
    "provisional_requires_uncertainty_reasons": (
        "Provisional decisions require at least one allowed uncertainty reason."
    ),
    "earned_requires_empty_uncertainty_reasons": (
        "Earned decisions require uncertainty_reasons: []."
    ),
    "earned_requires_evidence_refs": (
        "Earned decisions require at least one evidence_ref."
    ),
    "edits_required": (
        "Provide a nonempty edits[] array on the decision; put lane, "
        "expected_text, and replacement_text inside each edit row."
    ),
    "invalid_determination": (
        "Set determination to provisional or earned on the decision."
    ),
}


@dataclass(frozen=True)
class ValidatedEdit:
    lane: str
    expected_text: str
    replacement_text: str
    context_before: str | None
    context_after: str | None


@dataclass(frozen=True)
class ValidatedDecision:
    decision_id: str
    determination: str
    uncertainty_reasons: tuple[str, ...]
    verification_basis: str
    candidate_values: tuple[str, ...] | None
    evidence_refs: tuple[str, ...]
    edits: tuple[ValidatedEdit, ...]


@dataclass(frozen=True)
class ValidatedApplyTranscriptEditsRequest:
    base_revision_ref: str
    decisions: tuple[ValidatedDecision, ...]
    request_identity: str


_ALLOWED_REQUEST_KEYS = frozenset({"base_revision_ref", "decisions"})
_ALLOWED_DECISION_KEYS = frozenset(
    {
        "decision_id",
        "determination",
        "uncertainty_reasons",
        "verification_basis",
        "candidate_values",
        "evidence_refs",
        "edits",
    }
)
_ALLOWED_EDIT_KEYS = frozenset(
    {
        "lane",
        "expected_text",
        "replacement_text",
        "context_before",
        "context_after",
    }
)
_LANE_SET = frozenset(TRANSCRIPT_EDIT_LANES)


def validate_apply_transcript_edits_request(
    raw: Any,
) -> ValidatedApplyTranscriptEditsRequest:
    """Parse and validate a whole apply_transcript_edits request. Never truncates."""
    if type(raw) is not dict:
        raise ApplyTranscriptEditsContractError(
            "invalid_request",
            "Request must be a JSON object.",
        )
    unknown = sorted(set(raw) - _ALLOWED_REQUEST_KEYS)
    if unknown:
        raise ApplyTranscriptEditsContractError(
            "unknown_request_fields",
            f"Unknown fields: {unknown}",
            repair_hint=(
                "Remove unknown top-level fields. Allowed fields: "
                "base_revision_ref, decisions."
            ),
        )

    try:
        serialized = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ApplyTranscriptEditsContractError(
            "invalid_request",
            "Request is not JSON-serializable.",
        ) from exc
    if len(serialized) > MAX_REQUEST_SERIALIZED_CHARS:
        raise ApplyTranscriptEditsContractError(
            "request_too_large",
            f"Serialized request exceeds {MAX_REQUEST_SERIALIZED_CHARS} characters.",
        )

    base_ref = raw.get("base_revision_ref")
    if type(base_ref) is not str or not base_ref.strip():
        raise ApplyTranscriptEditsContractError(
            "base_revision_ref_required",
            "base_revision_ref must be a nonblank exact working revision ref.",
        )
    base_revision_ref = base_ref.strip()
    if base_revision_ref in {"transcript_edit:working", "transcript_edit:output"}:
        raise ApplyTranscriptEditsContractError(
            "aggregate_base_revision_ref_rejected",
            "base_revision_ref must be an exact immutable revision, not an aggregate alias.",
        )

    decisions_raw = raw.get("decisions")
    if type(decisions_raw) is not list:
        raise ApplyTranscriptEditsContractError(
            "decisions_required",
            "decisions must be a list.",
        )
    if not decisions_raw:
        raise ApplyTranscriptEditsContractError(
            "decisions_required",
            "decisions must be a non-empty list.",
        )
    if len(decisions_raw) > MAX_DECISIONS_PER_REQUEST:
        raise ApplyTranscriptEditsContractError(
            "too_many_decisions",
            f"At most {MAX_DECISIONS_PER_REQUEST} decisions per request.",
        )

    seen_ids: set[str] = set()
    decisions: list[ValidatedDecision] = []
    for index, item in enumerate(decisions_raw):
        decisions.append(_validate_decision(item, index=index, seen_ids=seen_ids))

    request_identity = _sha256_hex(serialized)
    return ValidatedApplyTranscriptEditsRequest(
        base_revision_ref=base_revision_ref,
        decisions=tuple(decisions),
        request_identity=request_identity,
    )


def _validate_decision(
    item: Any,
    *,
    index: int,
    seen_ids: set[str],
) -> ValidatedDecision:
    if type(item) is not dict:
        raise ApplyTranscriptEditsContractError(
            "invalid_decision",
            f"decisions[{index}] must be an object.",
        )
    unknown = sorted(set(item) - _ALLOWED_DECISION_KEYS)
    if unknown:
        nesting_misplaced = bool(_EDIT_ROW_FIELD_KEYS.intersection(unknown))
        raise ApplyTranscriptEditsContractError(
            "unknown_decision_fields",
            f"decisions[{index}] unknown fields: {unknown}",
            repair_hint=(
                _NESTING_REPAIR_HINT
                if nesting_misplaced
                else _UNKNOWN_DECISION_FIELD_REPAIR_HINT
            ),
        )

    decision_id = item.get("decision_id")
    if type(decision_id) is not str or not decision_id.strip():
        raise ApplyTranscriptEditsContractError(
            "decision_id_required",
            f"decisions[{index}].decision_id must be a nonblank string.",
            repair_hint=_REPAIR_HINTS_BY_REASON["decision_id_required"],
        )
    decision_id = decision_id.strip()
    if len(decision_id) > MAX_DECISION_ID_CHARS:
        raise ApplyTranscriptEditsContractError(
            "decision_id_too_long",
            f"decisions[{index}].decision_id exceeds {MAX_DECISION_ID_CHARS} characters.",
        )
    if decision_id in seen_ids:
        raise ApplyTranscriptEditsContractError(
            "duplicate_decision_id",
            f"Duplicate decision_id within request: {decision_id!r}",
        )
    seen_ids.add(decision_id)

    determination = item.get("determination")
    if type(determination) is not str or determination not in ALLOWED_DETERMINATIONS:
        raise ApplyTranscriptEditsContractError(
            "invalid_determination",
            f"decisions[{index}].determination must be one of "
            f"{sorted(ALLOWED_DETERMINATIONS)}.",
            repair_hint=_REPAIR_HINTS_BY_REASON["invalid_determination"],
        )

    basis = item.get("verification_basis")
    if type(basis) is not str or not basis.strip():
        raise ApplyTranscriptEditsContractError(
            "verification_basis_required",
            f"decisions[{index}].verification_basis must be a nonblank string.",
            repair_hint=_REPAIR_HINTS_BY_REASON["verification_basis_required"],
        )
    verification_basis = basis.strip()
    if len(verification_basis) > MAX_VERIFICATION_BASIS_CHARS:
        raise ApplyTranscriptEditsContractError(
            "verification_basis_too_long",
            f"decisions[{index}].verification_basis exceeds "
            f"{MAX_VERIFICATION_BASIS_CHARS} characters.",
        )

    evidence_refs = _validate_string_list(
        item.get("evidence_refs"),
        field=f"decisions[{index}].evidence_refs",
        required=True,
        max_items=MAX_EVIDENCE_REFS_PER_DECISION,
        allow_empty=True,
    )
    if determination == DETERMINATION_EARNED and not evidence_refs:
        raise ApplyTranscriptEditsContractError(
            "earned_requires_evidence_refs",
            f"decisions[{index}] determination 'earned' requires at least one evidence_ref.",
            repair_hint=_REPAIR_HINTS_BY_REASON["earned_requires_evidence_refs"],
        )

    uncertainty_reasons = _validate_uncertainty_reasons(
        item.get("uncertainty_reasons"),
        index=index,
        determination=determination,
    )

    candidate_values: tuple[str, ...] | None
    if "candidate_values" not in item or item.get("candidate_values") is None:
        candidate_values = None
    else:
        candidate_values = _validate_string_list(
            item.get("candidate_values"),
            field=f"decisions[{index}].candidate_values",
            required=True,
            max_items=MAX_CANDIDATE_VALUES_PER_DECISION,
            allow_empty=True,
        )

    edits_raw = item.get("edits")
    if type(edits_raw) is not list or not edits_raw:
        raise ApplyTranscriptEditsContractError(
            "edits_required",
            f"decisions[{index}].edits must be a non-empty list.",
            repair_hint=_REPAIR_HINTS_BY_REASON["edits_required"],
        )
    if len(edits_raw) > MAX_EDITS_PER_DECISION:
        raise ApplyTranscriptEditsContractError(
            "too_many_edits",
            f"decisions[{index}] exceeds {MAX_EDITS_PER_DECISION} edits.",
        )
    edits = tuple(
        _validate_edit(edit, decision_index=index, edit_index=ei)
        for ei, edit in enumerate(edits_raw)
    )
    return ValidatedDecision(
        decision_id=decision_id,
        determination=determination,
        uncertainty_reasons=uncertainty_reasons,
        verification_basis=verification_basis,
        candidate_values=candidate_values,
        evidence_refs=evidence_refs,
        edits=edits,
    )


def _validate_uncertainty_reasons(
    raw: Any,
    *,
    index: int,
    determination: str,
) -> tuple[str, ...]:
    field = f"decisions[{index}].uncertainty_reasons"
    if type(raw) is not list:
        raise ApplyTranscriptEditsContractError(
            "uncertainty_reasons_required",
            f"{field} must be a list.",
            repair_hint=_REPAIR_HINTS_BY_REASON["uncertainty_reasons_required"],
        )
    if len(raw) > MAX_UNCERTAINTY_REASONS_PER_DECISION:
        raise ApplyTranscriptEditsContractError(
            "too_many_uncertainty_reasons",
            f"{field} exceeds {MAX_UNCERTAINTY_REASONS_PER_DECISION} reasons.",
        )
    seen: set[str] = set()
    out: list[str] = []
    for reason_index, item in enumerate(raw):
        if type(item) is not str or item not in ALLOWED_UNCERTAINTY_REASONS:
            raise ApplyTranscriptEditsContractError(
                "invalid_uncertainty_reason",
                f"{field}[{reason_index}] must be one of "
                f"{sorted(ALLOWED_UNCERTAINTY_REASONS)}.",
            )
        if item in seen:
            raise ApplyTranscriptEditsContractError(
                "duplicate_uncertainty_reason",
                f"{field} contains duplicate reason {item!r}.",
            )
        seen.add(item)
        out.append(item)
    if determination == DETERMINATION_PROVISIONAL and not out:
        raise ApplyTranscriptEditsContractError(
            "provisional_requires_uncertainty_reasons",
            f"decisions[{index}] determination 'provisional' requires at least one "
            "uncertainty_reason.",
            repair_hint=_REPAIR_HINTS_BY_REASON["provisional_requires_uncertainty_reasons"],
        )
    if determination == DETERMINATION_EARNED and out:
        raise ApplyTranscriptEditsContractError(
            "earned_requires_empty_uncertainty_reasons",
            f"decisions[{index}] determination 'earned' requires uncertainty_reasons=[].",
            repair_hint=_REPAIR_HINTS_BY_REASON["earned_requires_empty_uncertainty_reasons"],
        )
    return tuple(out)


def _validate_edit(item: Any, *, decision_index: int, edit_index: int) -> ValidatedEdit:
    prefix = f"decisions[{decision_index}].edits[{edit_index}]"
    if type(item) is not dict:
        raise ApplyTranscriptEditsContractError(
            "invalid_edit",
            f"{prefix} must be an object.",
        )
    unknown = sorted(set(item) - _ALLOWED_EDIT_KEYS)
    if unknown:
        raise ApplyTranscriptEditsContractError(
            "unknown_edit_fields",
            f"{prefix} unknown fields: {unknown}",
        )

    lane = item.get("lane")
    if type(lane) is not str or lane not in _LANE_SET:
        raise ApplyTranscriptEditsContractError(
            "invalid_edit_lane",
            f"{prefix}.lane must be one of {list(TRANSCRIPT_EDIT_LANES)}.",
        )

    expected = item.get("expected_text")
    if type(expected) is not str or expected == "":
        raise ApplyTranscriptEditsContractError(
            "expected_text_required",
            f"{prefix}.expected_text must be a nonempty string.",
        )
    if len(expected) > MAX_EDIT_TEXT_CHARS:
        raise ApplyTranscriptEditsContractError(
            "edit_text_too_long",
            f"{prefix}.expected_text exceeds {MAX_EDIT_TEXT_CHARS} characters.",
        )

    replacement = item.get("replacement_text")
    if type(replacement) is not str:
        raise ApplyTranscriptEditsContractError(
            "replacement_text_required",
            f"{prefix}.replacement_text must be a string (empty string deletes).",
        )
    if len(replacement) > MAX_EDIT_TEXT_CHARS:
        raise ApplyTranscriptEditsContractError(
            "edit_text_too_long",
            f"{prefix}.replacement_text exceeds {MAX_EDIT_TEXT_CHARS} characters.",
        )

    context_before = (
        _optional_context(item.get("context_before"), field=f"{prefix}.context_before")
        if "context_before" in item
        else None
    )
    context_after = (
        _optional_context(item.get("context_after"), field=f"{prefix}.context_after")
        if "context_after" in item
        else None
    )

    return ValidatedEdit(
        lane=lane,
        expected_text=expected,
        replacement_text=replacement,
        context_before=context_before,
        context_after=context_after,
    )


def _optional_context(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise ApplyTranscriptEditsContractError(
            "invalid_context_text",
            f"{field} must be a string or null.",
        )
    if len(value) > MAX_CONTEXT_TEXT_CHARS:
        raise ApplyTranscriptEditsContractError(
            "context_text_too_long",
            f"{field} exceeds {MAX_CONTEXT_TEXT_CHARS} characters.",
        )
    return value


def _validate_string_list(
    value: Any,
    *,
    field: str,
    required: bool,
    max_items: int,
    allow_empty: bool,
) -> tuple[str, ...]:
    if value is None:
        if required:
            raise ApplyTranscriptEditsContractError(
                "invalid_string_list",
                f"{field} is required and must be a list of strings.",
            )
        return ()
    if type(value) is not list:
        raise ApplyTranscriptEditsContractError(
            "invalid_string_list",
            f"{field} must be a list of strings.",
        )
    if not allow_empty and not value:
        raise ApplyTranscriptEditsContractError(
            "invalid_string_list",
            f"{field} must be a non-empty list.",
        )
    if len(value) > max_items:
        raise ApplyTranscriptEditsContractError(
            "string_list_too_long",
            f"{field} exceeds {max_items} items.",
        )
    out: list[str] = []
    for i, item in enumerate(value):
        if type(item) is not str or not item.strip():
            raise ApplyTranscriptEditsContractError(
                "invalid_string_list_item",
                f"{field}[{i}] must be a nonblank string.",
            )
        out.append(item.strip())
    return tuple(out)


def _sha256_hex(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()
