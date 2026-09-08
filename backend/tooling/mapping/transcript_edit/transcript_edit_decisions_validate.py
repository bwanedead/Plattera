"""Canonical validator for persisted ``payload.transcript_edit_decisions`` (v1).

Shared by the apply engine and save/copy integrity boundary.
Fail closed: any present field must validate; absence means unmanaged/historical.

Enforces the same transport bounds and earned-evidence invariant as the apply
request contract so save/copy cannot preserve provenance the original request
could never have created.
"""

from __future__ import annotations

import json
from typing import Any

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    ALLOWED_DETERMINATIONS,
    DETERMINATION_EARNED,
    MAX_CANDIDATE_VALUES_PER_DECISION,
    MAX_CONTEXT_TEXT_CHARS,
    MAX_DECISION_ID_CHARS,
    MAX_DECISIONS_PER_REQUEST,
    MAX_EDIT_TEXT_CHARS,
    MAX_EDITS_PER_DECISION,
    MAX_EVIDENCE_REFS_PER_DECISION,
    MAX_REQUEST_SERIALIZED_CHARS,
    MAX_VERIFICATION_BASIS_CHARS,
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
    TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION,
    TRANSCRIPT_EDIT_LANES,
)


class PersistedProvenanceError(Exception):
    """Malformed or unsupported managed provenance."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail or "")
        message = self.reason_code if not self.detail else f"{self.reason_code}: {self.detail}"
        super().__init__(message)


_LANE_SET = frozenset(TRANSCRIPT_EDIT_LANES)
_ALLOWED_PROVENANCE_KEYS = frozenset({"schema_version", "decisions"})
_ALLOWED_DECISION_KEYS = frozenset(
    {
        "decision_id",
        "determination",
        "verification_basis",
        "candidate_values",
        "evidence_refs",
        "base_revision_ref",
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
        "start_offset",
        "end_offset",
    }
)


def managed_provenance_field_present(payload: Any) -> bool:
    """True when the payload object contains the provenance field at all."""
    return type(payload) is dict and TRANSCRIPT_EDIT_DECISIONS_FIELD in payload


def validate_persisted_transcript_edit_decisions(
    *,
    payload: dict[str, Any],
    require_present: bool = False,
) -> list[dict[str, Any]] | None:
    """Validate managed provenance on a payload.

    Returns:
      - None when the field is absent (historical/unmanaged), unless require_present.
      - list of validated decision dicts (shallow copies) when valid v1 is present.

    Raises PersistedProvenanceError on any present-but-invalid structure.
    """
    if type(payload) is not dict:
        raise PersistedProvenanceError(
            "malformed_provenance",
            "Payload must be an object when validating provenance.",
        )
    if TRANSCRIPT_EDIT_DECISIONS_FIELD not in payload:
        if require_present:
            raise PersistedProvenanceError(
                "malformed_provenance",
                "transcript_edit_decisions is required.",
            )
        return None

    block = payload.get(TRANSCRIPT_EDIT_DECISIONS_FIELD)
    if type(block) is not dict:
        raise PersistedProvenanceError(
            "malformed_provenance",
            "transcript_edit_decisions must be an object when present.",
        )
    unknown = sorted(set(block) - _ALLOWED_PROVENANCE_KEYS)
    if unknown:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"Unknown transcript_edit_decisions fields: {unknown}",
        )

    schema = block.get("schema_version")
    # Exact int equality — booleans are not schema versions.
    if type(schema) is not int or isinstance(schema, bool):
        raise PersistedProvenanceError(
            "malformed_provenance",
            "schema_version must be an exact integer.",
        )
    if schema != TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION:
        raise PersistedProvenanceError(
            "unsupported_provenance_schema",
            f"Only schema_version {TRANSCRIPT_EDIT_DECISIONS_SCHEMA_VERSION} is accepted; "
            f"got {schema!r}.",
        )

    decisions = block.get("decisions")
    if type(decisions) is not list:
        raise PersistedProvenanceError(
            "malformed_provenance",
            "transcript_edit_decisions.decisions must be a list.",
        )
    if len(decisions) > MAX_DECISIONS_PER_REQUEST:
        raise PersistedProvenanceError(
            "too_many_decisions",
            f"Persisted provenance exceeds {MAX_DECISIONS_PER_REQUEST} decisions.",
        )

    serialized = json.dumps(block, ensure_ascii=False, sort_keys=True)
    if len(serialized) > MAX_REQUEST_SERIALIZED_CHARS:
        raise PersistedProvenanceError(
            "request_too_large",
            f"Persisted provenance exceeds {MAX_REQUEST_SERIALIZED_CHARS} serialized characters.",
        )

    lane_text = {
        lane: payload[lane]
        for lane in TRANSCRIPT_EDIT_LANES
        if lane in payload and type(payload[lane]) is str
    }

    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []
    for index, item in enumerate(decisions):
        out.append(
            _validate_decision_record(
                item,
                index=index,
                seen_ids=seen_ids,
                lane_text=lane_text,
            )
        )
    return out


def _validate_decision_record(
    item: Any,
    *,
    index: int,
    seen_ids: set[str],
    lane_text: dict[str, str],
) -> dict[str, Any]:
    if type(item) is not dict:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}] must be an object.",
        )
    unknown = sorted(set(item) - _ALLOWED_DECISION_KEYS)
    if unknown:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}] unknown fields: {unknown}",
        )

    decision_id = item.get("decision_id")
    if type(decision_id) is not str or not decision_id.strip():
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}].decision_id must be a nonblank string.",
        )
    decision_id = decision_id.strip()
    if len(decision_id) > MAX_DECISION_ID_CHARS:
        raise PersistedProvenanceError(
            "decision_id_too_long",
            f"decisions[{index}].decision_id exceeds {MAX_DECISION_ID_CHARS} characters.",
        )
    if decision_id in seen_ids:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"Duplicate decision_id in persisted provenance: {decision_id!r}",
        )
    seen_ids.add(decision_id)

    determination = item.get("determination")
    if type(determination) is not str or determination not in ALLOWED_DETERMINATIONS:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}].determination invalid.",
        )

    basis = item.get("verification_basis")
    if type(basis) is not str or not basis.strip():
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}].verification_basis must be a nonblank string.",
        )
    verification_basis = basis.strip()
    if len(verification_basis) > MAX_VERIFICATION_BASIS_CHARS:
        raise PersistedProvenanceError(
            "verification_basis_too_long",
            f"decisions[{index}].verification_basis exceeds "
            f"{MAX_VERIFICATION_BASIS_CHARS} characters.",
        )

    base_ref = item.get("base_revision_ref")
    if type(base_ref) is not str or not base_ref.strip():
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}].base_revision_ref must be a nonblank string.",
        )

    evidence_refs = _validate_string_list(
        item.get("evidence_refs"),
        field=f"decisions[{index}].evidence_refs",
        allow_empty=True,
        max_items=MAX_EVIDENCE_REFS_PER_DECISION,
    )
    if determination == DETERMINATION_EARNED and not evidence_refs:
        raise PersistedProvenanceError(
            "earned_requires_evidence_refs",
            f"decisions[{index}] determination 'earned' requires at least one evidence_ref.",
        )

    candidate_values: list[str] | None
    if "candidate_values" not in item or item.get("candidate_values") is None:
        candidate_values = None
    else:
        candidate_values = list(
            _validate_string_list(
                item.get("candidate_values"),
                field=f"decisions[{index}].candidate_values",
                allow_empty=True,
                max_items=MAX_CANDIDATE_VALUES_PER_DECISION,
            )
        )

    edits_raw = item.get("edits")
    if type(edits_raw) is not list or not edits_raw:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"decisions[{index}].edits must be a non-empty list.",
        )
    if len(edits_raw) > MAX_EDITS_PER_DECISION:
        raise PersistedProvenanceError(
            "too_many_edits",
            f"decisions[{index}] exceeds {MAX_EDITS_PER_DECISION} edits.",
        )
    edits = [
        _validate_edit_record(edit, decision_index=index, edit_index=ei, lane_text=lane_text)
        for ei, edit in enumerate(edits_raw)
    ]

    record: dict[str, Any] = {
        "decision_id": decision_id,
        "determination": determination,
        "verification_basis": verification_basis,
        "evidence_refs": list(evidence_refs),
        "base_revision_ref": base_ref.strip(),
        "edits": edits,
    }
    if candidate_values is not None:
        record["candidate_values"] = candidate_values
    return record


def _validate_edit_record(
    item: Any,
    *,
    decision_index: int,
    edit_index: int,
    lane_text: dict[str, str],
) -> dict[str, Any]:
    prefix = f"decisions[{decision_index}].edits[{edit_index}]"
    if type(item) is not dict:
        raise PersistedProvenanceError("malformed_provenance", f"{prefix} must be an object.")
    unknown = sorted(set(item) - _ALLOWED_EDIT_KEYS)
    if unknown:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix} unknown fields: {unknown}",
        )

    lane = item.get("lane")
    if type(lane) is not str or lane not in _LANE_SET:
        raise PersistedProvenanceError("malformed_provenance", f"{prefix}.lane invalid.")

    expected = item.get("expected_text")
    if type(expected) is not str or expected == "":
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix}.expected_text must be a nonempty string.",
        )
    if len(expected) > MAX_EDIT_TEXT_CHARS:
        raise PersistedProvenanceError(
            "edit_text_too_long",
            f"{prefix}.expected_text exceeds {MAX_EDIT_TEXT_CHARS} characters.",
        )
    replacement = item.get("replacement_text")
    if type(replacement) is not str:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix}.replacement_text must be a string.",
        )
    if len(replacement) > MAX_EDIT_TEXT_CHARS:
        raise PersistedProvenanceError(
            "edit_text_too_long",
            f"{prefix}.replacement_text exceeds {MAX_EDIT_TEXT_CHARS} characters.",
        )

    for ctx_key in ("context_before", "context_after"):
        if ctx_key not in item:
            continue
        ctx = item.get(ctx_key)
        if ctx is not None and type(ctx) is not str:
            raise PersistedProvenanceError(
                "malformed_provenance",
                f"{prefix}.{ctx_key} must be a string or null.",
            )
        if type(ctx) is str and len(ctx) > MAX_CONTEXT_TEXT_CHARS:
            raise PersistedProvenanceError(
                "context_text_too_long",
                f"{prefix}.{ctx_key} exceeds {MAX_CONTEXT_TEXT_CHARS} characters.",
            )

    start = item.get("start_offset")
    end = item.get("end_offset")
    if type(start) is not int or isinstance(start, bool):
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix}.start_offset must be an exact non-boolean integer.",
        )
    if type(end) is not int or isinstance(end, bool):
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix}.end_offset must be an exact non-boolean integer.",
        )
    if start < 0 or end < 0 or end < start:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix} offsets must be non-negative with end >= start.",
        )
    if end - start != len(replacement):
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{prefix} end_offset - start_offset must equal len(replacement_text).",
        )

    text = lane_text.get(lane)
    if text is not None:
        if end > len(text):
            raise PersistedProvenanceError(
                "malformed_provenance",
                f"{prefix} offsets out of range for lane {lane!r}.",
            )
        if text[start:end] != replacement:
            raise PersistedProvenanceError(
                "stale_decision_span",
                f"{prefix} stored span no longer contains recorded replacement_text.",
            )

    return {
        "lane": lane,
        "expected_text": expected,
        "replacement_text": replacement,
        "context_before": item.get("context_before") if "context_before" in item else None,
        "context_after": item.get("context_after") if "context_after" in item else None,
        "start_offset": start,
        "end_offset": end,
    }


def _validate_string_list(
    value: Any,
    *,
    field: str,
    allow_empty: bool,
    max_items: int,
) -> tuple[str, ...]:
    if type(value) is not list:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{field} must be a list of strings.",
        )
    if not allow_empty and not value:
        raise PersistedProvenanceError(
            "malformed_provenance",
            f"{field} must be non-empty.",
        )
    if len(value) > max_items:
        raise PersistedProvenanceError(
            "string_list_too_long",
            f"{field} exceeds {max_items} items.",
        )
    out: list[str] = []
    for i, item in enumerate(value):
        if type(item) is not str or not item.strip():
            raise PersistedProvenanceError(
                "malformed_provenance",
                f"{field}[{i}] must be a nonblank string.",
            )
        out.append(item.strip())
    return tuple(out)


def assert_revision_and_payload_evidence_coherent(
    *,
    revision_evidence_refs: list[str],
    payload: dict[str, Any],
) -> None:
    """Refuse when payload.evidence_refs is present and disagrees with revision-level list."""
    if "evidence_refs" not in payload:
        return
    payload_refs = payload.get("evidence_refs")
    if type(payload_refs) is not list:
        raise PersistedProvenanceError(
            "conflicting_evidence_representation",
            "payload.evidence_refs must be a list when present.",
        )
    normalized_payload: list[str] = []
    for i, item in enumerate(payload_refs):
        if type(item) is not str or not item.strip():
            raise PersistedProvenanceError(
                "conflicting_evidence_representation",
                f"payload.evidence_refs[{i}] must be a nonblank string.",
            )
        normalized_payload.append(item.strip())
    if normalized_payload != list(revision_evidence_refs):
        raise PersistedProvenanceError(
            "conflicting_evidence_representation",
            "payload.evidence_refs differs from revision-level evidence_refs.",
        )
