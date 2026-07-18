"""Keyless minimal views for hydrate_deed_to_ir_input."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tooling.mapping.deed_to_ir.mapping_operands_projection import (
    compact_mapping_operands_for_projection,
)

from .result_view_common import (
    MAX_COLLECTION_ROWS,
    MAX_ERROR_MESSAGE_CHARS,
    MAX_REQUESTED_RESOLUTION_UNIT_IDS,
    bound_message,
    fit_complete_strings,
    json_native,
    mapping_rows,
    payload_fits,
    section_omission,
    strict_string_list,
    string_rows,
    strip_host_value,
    try_attach_value,
    try_build_view,
)

SCHEMA_HYDRATE_DEED_TO_IR_INPUT = "deed_to_ir.hydrate_deed_to_ir_input.v1"

_SECTION_KEYS = (
    "normalized_transcript",
    "verbatim_transcript",
    "issues",
    "hitl_decisions",
    "parcel_metadata",
    "evidence_refs",
    "mapping_operands",
    "resolution_state",
    "inherited_handoff_conditions",
)

_TOP_LEVEL_META = frozenset(
    {
        "sections",
        "results",
        "errors",
        "hydrated_section_count",
        "inherited_handoff_conditions",
    }
)

_RESOLUTION_IDENTITY_KEYS = (
    "projection_mode",
    "resolution_state_ref",
    "schema_version",
    "active_item_id",
    "totals",
    "filter",
    "truncation",
)

MAX_ERROR_ROWS = 16

_AttachOutcome = str  # attached | absent | invalid_shape | view_budget


def build_hydrate_deed_to_ir_input_view(
    outputs: Mapping[str, Any],
    *,
    action_inputs: Mapping[str, Any] | None = None,
):
    """Keyless hydrate-input view. Always continuity_key=None."""
    request = action_inputs if isinstance(action_inputs, Mapping) else {}
    requested_sections = strict_string_list(request.get("sections"))
    returned_sections = strict_string_list(outputs.get("sections"))
    section_order = requested_sections or returned_sections or list(_SECTION_KEYS)
    all_resolution_ids = strict_string_list(request.get("resolution_unit_ids"))

    results = _results_map(outputs)
    errors = _project_errors(outputs.get("errors"))

    # Request-derived lanes stay out of the base until after content fits.
    base: dict[str, Any] = {"lane": "hydrate_deed_to_ir_input"}
    hydrated_count = outputs.get("hydrated_section_count")
    if isinstance(hydrated_count, int) and hydrated_count >= 0 and not isinstance(
        hydrated_count, bool
    ):
        base["hydrated_section_count"] = hydrated_count

    payload = dict(base)
    fit_complete_strings(
        payload,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        key="returned_sections",
        values=returned_sections,
        omitted_key="returned_sections_omitted_count",
    )
    fit_complete_strings(
        payload,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        key="requested_sections",
        values=requested_sections,
        omitted_key="requested_sections_omitted_count",
    )

    sections_omitted: list[dict[str, Any]] = []
    error_codes = _error_section_codes(errors)

    for key in section_order:
        if key not in _SECTION_KEYS:
            continue
        raw, present = _lookup_section(outputs, results, key)
        if not present:
            reason = "tooling_error" if key in error_codes else "absent"
            sections_omitted.append(section_omission(section=key, reason=reason))
            continue

        outcome, extra = _attach_section(payload, key=key, raw=raw)
        if outcome == "attached":
            continue
        if outcome == "invalid_shape":
            sections_omitted.append(
                section_omission(section=key, reason="invalid_shape")
            )
            continue
        if outcome == "view_budget":
            sections_omitted.append(
                section_omission(section=key, reason="view_budget", **extra)
            )
            continue
        reason = "tooling_error" if key in error_codes else "absent"
        sections_omitted.append(section_omission(section=key, reason=reason))

    # Content → omission descriptors → request IDs → errors.
    fitted_omissions: list[dict[str, Any]] = []
    for row in sections_omitted:
        candidate = {**payload, "sections_omitted": [*fitted_omissions, row]}
        if not payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=candidate
        ):
            break
        fitted_omissions.append(row)
    if fitted_omissions:
        payload["sections_omitted"] = fitted_omissions
    if sections_omitted:
        count_candidate = {
            **payload,
            "sections_omitted_count": len(sections_omitted),
        }
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=count_candidate
        ):
            payload["sections_omitted_count"] = len(sections_omitted)

    fit_complete_strings(
        payload,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        key="requested_resolution_unit_ids",
        values=all_resolution_ids,
        omitted_key="resolution_unit_ids_omitted_count",
        intake_limit=MAX_REQUESTED_RESOLUTION_UNIT_IDS,
    )

    fitted_errors: list[dict[str, Any]] = []
    for row in errors[:MAX_ERROR_ROWS]:
        candidate = {**payload, "errors": [*fitted_errors, row]}
        if not payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=candidate
        ):
            break
        fitted_errors.append(row)
    if fitted_errors:
        payload["errors"] = fitted_errors
    if errors:
        considered = errors[:MAX_ERROR_ROWS]
        omitted_count = max(0, len(errors) - len(considered)) + max(
            0, len(considered) - len(fitted_errors)
        )
        if omitted_count:
            count_candidate = {**payload, "errors_omitted_count": omitted_count}
            if payload_fits(
                schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=count_candidate
            ):
                payload["errors_omitted_count"] = omitted_count

    return try_build_view(
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        payload=payload,
        continuity_key=None,
    )


def _results_map(outputs: Mapping[str, Any]) -> Mapping[str, Any]:
    results = outputs.get("results")
    return results if isinstance(results, Mapping) else {}


def _lookup_section(
    outputs: Mapping[str, Any],
    results: Mapping[str, Any],
    key: str,
) -> tuple[Any, bool]:
    """Presence is key membership, not truthiness."""
    if key == "mapping_operands":
        if "mapping_operands" in outputs and isinstance(
            outputs.get("mapping_operands"), Mapping
        ):
            return outputs["mapping_operands"], True
        if "mapping_operands" in results:
            return results["mapping_operands"], True
        return None, False

    if key in results:
        return results[key], True
    if key in outputs and key not in _TOP_LEVEL_META:
        return outputs[key], True
    if key == "inherited_handoff_conditions" and key in outputs:
        return outputs[key], True
    return None, False


def _normalize_section(key: str, raw: Any) -> tuple[str, Any | None]:
    if raw is None:
        return "absent", None

    if key in ("normalized_transcript", "verbatim_transcript"):
        if isinstance(raw, str):
            return ("empty" if raw == "" else "content"), raw
        if isinstance(raw, Mapping) and "text" in raw:
            text = raw.get("text")
            if not isinstance(text, str):
                return "invalid_shape", None
            return ("empty" if text == "" else "content"), text
        return "invalid_shape", None

    if key == "issues":
        return _normalize_list_wrapper(raw, wrapper_key="issues")
    if key == "hitl_decisions":
        return _normalize_list_wrapper(raw, wrapper_key="hitl_decisions")
    if key == "evidence_refs":
        return _normalize_list_wrapper(raw, wrapper_key="evidence_refs")

    if key == "parcel_metadata":
        if isinstance(raw, Mapping) and "parcel_metadata" in raw:
            inner = raw.get("parcel_metadata")
            if not isinstance(inner, Mapping):
                return "invalid_shape", None
            return ("empty" if len(inner) == 0 else "content"), dict(inner)
        if isinstance(raw, Mapping):
            return ("empty" if len(raw) == 0 else "content"), dict(raw)
        return "invalid_shape", None

    if key in (
        "mapping_operands",
        "resolution_state",
        "inherited_handoff_conditions",
    ):
        if not isinstance(raw, Mapping):
            return "invalid_shape", None
        return ("empty" if len(raw) == 0 else "content"), dict(raw)

    return "invalid_shape", None


def _normalize_list_wrapper(raw: Any, *, wrapper_key: str) -> tuple[str, Any | None]:
    if isinstance(raw, list):
        return ("empty" if len(raw) == 0 else "content"), list(raw)
    if isinstance(raw, Mapping) and wrapper_key in raw:
        inner = raw.get(wrapper_key)
        if not isinstance(inner, list):
            return "invalid_shape", None
        return ("empty" if len(inner) == 0 else "content"), list(inner)
    return "invalid_shape", None


def _attach_section(
    payload: dict[str, Any],
    *,
    key: str,
    raw: Any,
) -> tuple[_AttachOutcome, dict[str, Any]]:
    status, normalized = _normalize_section(key, raw)
    if status == "absent":
        return "absent", {}
    if status == "invalid_shape":
        return "invalid_shape", {}

    if key in ("normalized_transcript", "verbatim_transcript"):
        text = normalized if isinstance(normalized, str) else ""
        if try_attach_value(
            payload,
            key=key,
            value=text,
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        ):
            return "attached", {}
        return "view_budget", {"returned_text_chars": len(text)}

    if key in ("issues", "hitl_decisions"):
        return _attach_mapping_rows(payload, key=key, raw=normalized), {}

    if key == "evidence_refs":
        return _attach_string_rows(payload, key=key, raw=normalized), {}

    if key == "parcel_metadata":
        meta = json_native(
            strip_host_value(normalized if isinstance(normalized, Mapping) else {})
        )
        if try_attach_value(
            payload,
            key=key,
            value=meta if isinstance(meta, Mapping) else {},
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        ):
            return "attached", {}
        return "view_budget", {}

    if key == "mapping_operands":
        return _attach_mapping_operands(payload, normalized), {}

    if key == "resolution_state":
        return _attach_resolution_state(payload, normalized), {}

    if key == "inherited_handoff_conditions":
        value = json_native(strip_host_value(normalized))
        if try_attach_value(
            payload,
            key=key,
            value=value,
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
        ):
            return "attached", {}
        return "view_budget", {}

    return "invalid_shape", {}


def _attach_mapping_rows(
    payload: dict[str, Any], *, key: str, raw: Any
) -> _AttachOutcome:
    if not isinstance(raw, list):
        return "invalid_shape"
    if len(raw) == 0:
        return (
            "attached"
            if try_attach_value(
                payload,
                key=key,
                value=[],
                schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
            )
            else "view_budget"
        )

    rows, intake_omitted = mapping_rows(raw, limit=MAX_COLLECTION_ROWS)
    kept: list[dict[str, Any]] = []
    for row in rows:
        trial = list(kept) + [row]
        trial_omitted = intake_omitted + (len(rows) - len(trial))
        candidate = {**payload, key: trial}
        if trial_omitted:
            candidate[f"{key}_omitted_count"] = trial_omitted
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=candidate
        ):
            kept = trial
            continue
        # Skip oversized row; continue fitting later rows.
        continue

    omitted = intake_omitted + (len(rows) - len(kept))
    final = {**payload, key: kept}
    if omitted:
        final[f"{key}_omitted_count"] = omitted
    if not payload_fits(schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=final):
        # Keep rows without count if count is what fails.
        final = {**payload, key: kept}
        if not payload_fits(schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=final):
            return "view_budget"
    payload[key] = kept
    if omitted and f"{key}_omitted_count" in final:
        payload[f"{key}_omitted_count"] = omitted
    elif omitted:
        count_candidate = {**payload, f"{key}_omitted_count": omitted}
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=count_candidate
        ):
            payload[f"{key}_omitted_count"] = omitted
    return "attached"


def _attach_string_rows(
    payload: dict[str, Any], *, key: str, raw: Any
) -> _AttachOutcome:
    if not isinstance(raw, list):
        return "invalid_shape"
    if len(raw) == 0:
        return (
            "attached"
            if try_attach_value(
                payload,
                key=key,
                value=[],
                schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
            )
            else "view_budget"
        )

    rows, intake_omitted = string_rows(raw, limit=MAX_COLLECTION_ROWS)
    # string_rows skips non-strings; also count valid empty? only nonblank.
    # Preserve blank-skipped? evidence refs are nonblank strings from tooling.
    kept: list[str] = []
    for row in rows:
        trial = list(kept) + [row]
        trial_omitted = intake_omitted + (len(rows) - len(trial))
        candidate = {**payload, key: trial}
        if trial_omitted:
            candidate[f"{key}_omitted_count"] = trial_omitted
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=candidate
        ):
            kept = trial
            continue
        continue

    omitted = intake_omitted + (len(rows) - len(kept))
    payload[key] = kept
    if omitted:
        count_candidate = {**payload, f"{key}_omitted_count": omitted}
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=count_candidate
        ):
            payload[f"{key}_omitted_count"] = omitted
    return "attached"


def _attach_mapping_operands(payload: dict[str, Any], raw: Any) -> _AttachOutcome:
    if not isinstance(raw, Mapping):
        return "invalid_shape"

    groups_raw = raw.get("operand_groups")
    operands_raw = raw.get("operands")
    if groups_raw is not None and not isinstance(groups_raw, list):
        return "invalid_shape"
    if operands_raw is not None and not isinstance(operands_raw, list):
        return "invalid_shape"

    source_groups = [
        item for item in (groups_raw if isinstance(groups_raw, list) else [])
        if isinstance(item, Mapping)
    ]
    source_operands = [
        item for item in (operands_raw if isinstance(operands_raw, list) else [])
        if isinstance(item, Mapping)
    ]

    tooling_trunc = (
        raw.get("truncation") if isinstance(raw.get("truncation"), Mapping) else {}
    )
    tooling_groups_omitted = int(tooling_trunc.get("operand_groups_omitted") or 0)
    tooling_operands_omitted = int(
        tooling_trunc.get("operands_omitted")
        or tooling_trunc.get("operand_rows_omitted")
        or 0
    )

    compact = compact_mapping_operands_for_projection({"mapping_operands": raw})
    if not isinstance(compact, Mapping):
        # Empty successful source still projects identity when present.
        compact = {
            key: raw[key]
            for key in ("operand_suite_ref", "projection_mode", "totals", "truncation")
            if key in raw and raw[key] is not None
        }

    source = json_native(strip_host_value(dict(compact)))
    if not isinstance(source, Mapping):
        return "invalid_shape"

    identity: dict[str, Any] = {}
    for key in ("operand_suite_ref", "projection_mode", "totals", "truncation"):
        if key in source and source[key] is not None:
            identity[key] = source[key]

    compact_groups = [
        item
        for item in (source.get("operand_groups") or [])
        if isinstance(item, Mapping)
    ]
    compact_operands = [
        item for item in (source.get("operands") or []) if isinstance(item, Mapping)
    ]

    projector_groups_omitted = max(0, len(source_groups) - len(compact_groups))
    projector_operands_omitted = max(0, len(source_operands) - len(compact_operands))

    kept_groups: list[dict[str, Any]] = []
    for row in compact_groups:
        trial = list(kept_groups) + [dict(row)]
        block = _operands_block(
            identity,
            groups=trial,
            operands=[],
            groups_omitted=tooling_groups_omitted
            + projector_groups_omitted
            + (len(compact_groups) - len(trial)),
            operands_omitted=tooling_operands_omitted
            + projector_operands_omitted
            + len(compact_operands),
        )
        trial_payload = {**payload, "mapping_operands": block}
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=trial_payload
        ):
            kept_groups = trial
            continue
        continue

    kept_operands: list[dict[str, Any]] = []
    for row in compact_operands:
        trial = list(kept_operands) + [dict(row)]
        block = _operands_block(
            identity,
            groups=kept_groups,
            operands=trial,
            groups_omitted=tooling_groups_omitted
            + projector_groups_omitted
            + (len(compact_groups) - len(kept_groups)),
            operands_omitted=tooling_operands_omitted
            + projector_operands_omitted
            + (len(compact_operands) - len(trial)),
        )
        trial_payload = {**payload, "mapping_operands": block}
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=trial_payload
        ):
            kept_operands = trial
            continue
        continue

    groups_omitted = (
        tooling_groups_omitted
        + projector_groups_omitted
        + (len(compact_groups) - len(kept_groups))
    )
    operands_omitted = (
        tooling_operands_omitted
        + projector_operands_omitted
        + (len(compact_operands) - len(kept_operands))
    )
    block = _operands_block(
        identity,
        groups=kept_groups,
        operands=kept_operands,
        groups_omitted=groups_omitted,
        operands_omitted=operands_omitted,
    )
    if not block and not identity:
        block = dict(identity)
    if try_attach_value(
        payload,
        key="mapping_operands",
        value=block,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
    ):
        return "attached"
    lean = _operands_block(
        identity,
        groups=kept_groups,
        operands=kept_operands,
        groups_omitted=0,
        operands_omitted=0,
    )
    if try_attach_value(
        payload,
        key="mapping_operands",
        value=lean,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
    ):
        return "attached"
    return "view_budget"


def _operands_block(
    identity: Mapping[str, Any],
    *,
    groups: Sequence[Mapping[str, Any]],
    operands: Sequence[Mapping[str, Any]],
    groups_omitted: int,
    operands_omitted: int,
) -> dict[str, Any]:
    block = dict(identity)
    if groups:
        block["operand_groups"] = [dict(row) for row in groups]
    if operands:
        block["operands"] = [dict(row) for row in operands]
    if groups_omitted:
        block["operand_groups_omitted_count"] = groups_omitted
    if operands_omitted:
        block["operands_omitted_count"] = operands_omitted
    return block


def _attach_resolution_state(payload: dict[str, Any], raw: Any) -> _AttachOutcome:
    if not isinstance(raw, Mapping):
        return "invalid_shape"
    if "items" in raw and not isinstance(raw.get("items"), list):
        return "invalid_shape"
    if "relations" in raw and not isinstance(raw.get("relations"), list):
        return "invalid_shape"

    identity: dict[str, Any] = {}
    for key in _RESOLUTION_IDENTITY_KEYS:
        if key in raw and raw[key] is not None:
            identity[key] = json_native(strip_host_value(raw[key]))

    tooling_trunc = (
        raw.get("truncation") if isinstance(raw.get("truncation"), Mapping) else {}
    )
    tooling_items_omitted = int(tooling_trunc.get("items_omitted") or 0)
    tooling_relations_omitted = int(tooling_trunc.get("relations_omitted") or 0)

    items_raw = raw.get("items") if isinstance(raw.get("items"), list) else []
    relations_raw = (
        raw.get("relations") if isinstance(raw.get("relations"), list) else []
    )
    # Index / selected modes may omit relations key entirely; treat absent as empty list
    # only when key missing. Present malformed already rejected above.
    relations_present = "relations" in raw
    items_present = "items" in raw

    item_rows, items_intake = mapping_rows(items_raw, limit=MAX_COLLECTION_ROWS)
    relation_rows, relations_intake = mapping_rows(
        relations_raw, limit=MAX_COLLECTION_ROWS
    )

    kept_items: list[dict[str, Any]] = []
    for row in item_rows:
        trial = list(kept_items) + [row]
        block = _resolution_block(
            identity,
            items=trial if items_present or trial else None,
            relations=[] if relations_present else None,
            items_omitted=tooling_items_omitted
            + items_intake
            + (len(item_rows) - len(trial)),
            relations_omitted=tooling_relations_omitted
            + relations_intake
            + len(relation_rows),
            include_items=items_present or bool(item_rows),
            include_relations=relations_present,
        )
        trial_payload = {**payload, "resolution_state": block}
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=trial_payload
        ):
            kept_items = trial
            continue
        continue

    kept_relations: list[dict[str, Any]] = []
    for row in relation_rows:
        trial = list(kept_relations) + [row]
        block = _resolution_block(
            identity,
            items=kept_items if (items_present or kept_items) else None,
            relations=trial,
            items_omitted=tooling_items_omitted
            + items_intake
            + (len(item_rows) - len(kept_items)),
            relations_omitted=tooling_relations_omitted
            + relations_intake
            + (len(relation_rows) - len(trial)),
            include_items=items_present or bool(item_rows) or bool(kept_items),
            include_relations=True,
        )
        trial_payload = {**payload, "resolution_state": block}
        if payload_fits(
            schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT, payload=trial_payload
        ):
            kept_relations = trial
            continue
        continue

    items_omitted = (
        tooling_items_omitted + items_intake + (len(item_rows) - len(kept_items))
    )
    relations_omitted = (
        tooling_relations_omitted
        + relations_intake
        + (len(relation_rows) - len(kept_relations))
    )
    block = _resolution_block(
        identity,
        items=kept_items if (items_present or kept_items) else None,
        relations=kept_relations if relations_present else None,
        items_omitted=items_omitted,
        relations_omitted=relations_omitted,
        include_items=items_present or bool(kept_items) or bool(item_rows),
        include_relations=relations_present,
    )
    if try_attach_value(
        payload,
        key="resolution_state",
        value=block,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
    ):
        return "attached"
    lean = _resolution_block(
        identity,
        items=kept_items if (items_present or kept_items) else None,
        relations=kept_relations if relations_present else None,
        items_omitted=0,
        relations_omitted=0,
        include_items=items_present or bool(kept_items) or bool(item_rows),
        include_relations=relations_present,
    )
    if try_attach_value(
        payload,
        key="resolution_state",
        value=lean,
        schema_id=SCHEMA_HYDRATE_DEED_TO_IR_INPUT,
    ):
        return "attached"
    return "view_budget"


def _resolution_block(
    identity: Mapping[str, Any],
    *,
    items: Sequence[Mapping[str, Any]] | None,
    relations: Sequence[Mapping[str, Any]] | None,
    items_omitted: int,
    relations_omitted: int,
    include_items: bool,
    include_relations: bool,
) -> dict[str, Any]:
    block = dict(identity)
    if include_items:
        block["items"] = [dict(row) for row in (items or [])]
    if include_relations:
        block["relations"] = [dict(row) for row in (relations or [])]
    if items_omitted:
        block["items_omitted_count"] = items_omitted
    if relations_omitted:
        block["relations_omitted_count"] = relations_omitted
    return block


def _project_errors(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        row: dict[str, Any] = {}
        section = item.get("section")
        code = item.get("code")
        reason = item.get("reason")
        if isinstance(section, str) and section.strip():
            row["section"] = section.strip()
        if isinstance(code, str) and code.strip():
            row["code"] = code.strip()
        if isinstance(reason, str) and reason.strip():
            row["reason"] = reason.strip()
        msg = bound_message(item.get("message"))
        if msg:
            row.update(msg)
        elif isinstance(item.get("message"), str):
            text = item["message"]
            if len(text) > MAX_ERROR_MESSAGE_CHARS:
                row["message_omitted"] = True
                row["message_chars"] = len(text)
        for key in ("omitted_count", "resolution_unit_id"):
            if key in item and item[key] is not None:
                row[key] = item[key]
        if row:
            rows.append(row)
    return rows


def _error_section_codes(errors: Sequence[Mapping[str, Any]]) -> dict[str, str | None]:
    out: dict[str, str | None] = {}
    for row in errors:
        section = row.get("section")
        if isinstance(section, str) and section.strip() and section not in out:
            code = row.get("code") or row.get("reason")
            out[section] = code if isinstance(code, str) else None
    return out
