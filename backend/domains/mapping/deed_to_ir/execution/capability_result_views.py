"""Deed-to-IR capability AgentResultView builder (keyless, request-aware)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from tooling.mapping.deed_to_ir.read_action_projection import (
    compact_feature_graph_capabilities_summary,
)

from .result_view_common import (
    MAX_IGNORED_OPERATION_ROWS,
    MAX_REQUESTED_OPERATION_NAMES,
    bound_text,
    bounded_ignored_operation_rows,
    fit_complete_strings,
    payload_fits,
    section_omission,
    strict_string_list,
    try_attach_value,
    try_build_view,
)

SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES = (
    "deed_to_ir.describe_feature_graph_capabilities.v1"
)


def build_describe_feature_graph_capabilities_view(
    outputs: Mapping[str, Any],
    *,
    action_inputs: Mapping[str, Any] | None = None,
):
    """Keyless capability view: coherent sections, no operation recommendations."""
    inputs = action_inputs if isinstance(action_inputs, Mapping) else None
    requested = strict_string_list(inputs.get("sections") if inputs else None)
    returned = strict_string_list(outputs.get("sections"))
    order = requested or returned
    explicit_operation_request = bool(
        inputs is not None and "operation_names" in inputs
    )
    all_requested_ops = strict_string_list(
        inputs.get("operation_names") if inputs else None
    )

    summary = None
    if "starter_contract" in order:
        summary = compact_feature_graph_capabilities_summary(
            outputs, action_inputs=inputs
        )

    # Request-derived operation names stay out of the base until after content.
    payload: dict[str, Any] = {"lane": "feature_graph_capabilities"}
    fit_complete_strings(
        payload,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        key="returned_sections",
        values=returned,
        omitted_key="returned_sections_omitted_count",
    )
    fit_complete_strings(
        payload,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        key="requested_sections",
        values=requested,
        omitted_key="requested_sections_omitted_count",
    )

    sections_omitted: list[dict[str, Any]] = []

    for section in order:
        ok = _attach_capability_section(
            payload,
            outputs=outputs,
            summary=summary,
            section=section,
            explicit_operation_request=explicit_operation_request,
        )
        if ok is True:
            continue
        if ok is False:
            sections_omitted.append(section_omission(section=section))

    # Content → omission descriptors → requested op names → ignored diagnostics.
    fitted_omissions: list[dict[str, Any]] = []
    for row in sections_omitted:
        candidate = {**payload, "sections_omitted": [*fitted_omissions, row]}
        if not payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES, payload=candidate
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
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
            payload=count_candidate,
        ):
            payload["sections_omitted_count"] = len(sections_omitted)

    fit_complete_strings(
        payload,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        key="requested_operation_names",
        values=all_requested_ops,
        omitted_key="operation_names_omitted_count",
        intake_limit=MAX_REQUESTED_OPERATION_NAMES,
    )

    ignored_rows, ignored_intake_omitted = bounded_ignored_operation_rows(
        outputs.get("ignored_operation_names"),
        limit=MAX_IGNORED_OPERATION_ROWS,
    )
    fitted_ignored: list[dict[str, Any]] = []
    for row in ignored_rows:
        candidate = {
            **payload,
            "ignored_operation_names": [*fitted_ignored, row],
        }
        if not payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES, payload=candidate
        ):
            break
        fitted_ignored.append(row)
    if fitted_ignored:
        payload["ignored_operation_names"] = fitted_ignored
    ignored_total_omitted = ignored_intake_omitted + max(
        0, len(ignored_rows) - len(fitted_ignored)
    )
    if ignored_total_omitted:
        count_candidate = {
            **payload,
            "ignored_operation_names_omitted_count": ignored_total_omitted,
        }
        if payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
            payload=count_candidate,
        ):
            payload["ignored_operation_names_omitted_count"] = ignored_total_omitted

    return try_build_view(
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        payload=payload,
        continuity_key=None,
    )


def _attach_capability_section(
    payload: dict[str, Any],
    *,
    outputs: Mapping[str, Any],
    summary: Mapping[str, Any] | None,
    section: str,
    explicit_operation_request: bool,
) -> bool | None:
    """Return True if attached, False if omitted, None if section absent from outputs."""
    if section == "starter_contract":
        return _attach_starter(payload, outputs=outputs, summary=summary)
    if section == "operations":
        return _attach_operations(
            payload,
            outputs=outputs,
            explicit_operation_request=explicit_operation_request,
        )
    if section == "core_schema":
        return _attach_schema_section(
            payload,
            outputs=outputs,
            section="core_schema",
            models_key="model_schemas",
            identity_keys=(
                "feature_graph_request_schema",
                "feature_kinds",
                "content_rules",
                "geometry_contract",
                "edge_type_contract",
            ),
        )
    if section == "provenance":
        return _attach_schema_section(
            payload,
            outputs=outputs,
            section="provenance",
            models_key="provenance_schemas",
            identity_keys=("provenance_rules",),
        )
    if section == "examples":
        return _attach_examples(payload, outputs.get("examples"))
    if section == "artifact_refs":
        value = {
            key: outputs[key]
            for key in ("artifact_types", "artifact_ref_prefixes")
            if key in outputs
        }
        if not value:
            return None
        return try_attach_value(
            payload,
            key="artifact_refs",
            value=value,
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        )
    if section == "validation_schema":
        return _attach_validation_schema(
            payload, outputs.get("canonical_feature_graph_json_schema")
        )
    return None


def _attach_starter(
    payload: dict[str, Any],
    *,
    outputs: Mapping[str, Any],
    summary: Mapping[str, Any] | None,
) -> bool | None:
    starter = None
    if isinstance(summary, Mapping) and isinstance(
        summary.get("starter_contract"), Mapping
    ):
        starter = dict(summary["starter_contract"])
    elif isinstance(outputs.get("starter_contract"), Mapping):
        starter = dict(outputs["starter_contract"])
    if starter is None:
        return None
    card = starter.get("first_draft_authoring_card")
    if not isinstance(card, Mapping):
        top = outputs.get("first_draft_authoring_card")
        if isinstance(top, Mapping):
            starter["first_draft_authoring_card"] = dict(top)
    return try_attach_value(
        payload,
        key="starter_contract",
        value=starter,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    )


def _attach_operations(
    payload: dict[str, Any],
    *,
    outputs: Mapping[str, Any],
    explicit_operation_request: bool,
) -> bool | None:
    ops_raw = outputs.get("registered_operations")
    if not isinstance(ops_raw, list):
        return None
    contract = outputs.get("operation_contract")
    identity: dict[str, Any] = {}
    if isinstance(contract, Mapping):
        identity["operation_contract"] = dict(contract)

    if explicit_operation_request:
        # Tooling already resolved valid operations; do not re-filter by request intake.
        rows = [
            _compact_operation_row(row)
            for row in ops_raw
            if isinstance(row, Mapping)
        ]
        rows = [row for row in rows if row]
        return _fit_requested_operations(payload, identity=identity, rows=rows)

    # Bounded compact index — do not expand every full contract.
    rows = []
    for row in ops_raw:
        if not isinstance(row, Mapping):
            continue
        rows.append(
            {
                key: row[key]
                for key in ("name", "category", "compiler_support", "compile_note")
                if key in row and row[key] is not None
            }
        )
    return _fit_operation_index(payload, identity=identity, rows=rows)


def _fit_requested_operations(
    payload: dict[str, Any],
    *,
    identity: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> bool:
    """Skip individually oversized requested rows; continue fitting later rows."""
    kept: list[dict[str, Any]] = []
    skipped_names: list[str] = []
    for row in rows:
        name = row.get("name")
        trial = list(kept) + [dict(row)]
        block = _operations_block(identity, kept=trial, omitted_names=())
        trial_payload = dict(payload)
        trial_payload["operations"] = block
        if payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
            payload=trial_payload,
        ):
            kept = trial
            continue
        if isinstance(name, str) and name.strip():
            skipped_names.append(name.strip())

    fitted_omitted: list[dict[str, str]] = []
    for name in skipped_names:
        row = {"name": name, "reason": "view_budget"}
        block = _operations_block(
            identity,
            kept=kept,
            omitted_names=[r["name"] for r in fitted_omitted] + [name],
        )
        trial_payload = dict(payload)
        trial_payload["operations"] = block
        if not payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
            payload=trial_payload,
        ):
            break
        fitted_omitted.append(row)

    block = _operations_block(
        identity,
        kept=kept,
        omitted_names=[row["name"] for row in fitted_omitted],
        omitted_count=len(skipped_names),
    )
    if not block:
        return False
    return try_attach_value(
        payload,
        key="operations",
        value=block,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    )


def _operations_block(
    identity: Mapping[str, Any],
    *,
    kept: Sequence[Mapping[str, Any]],
    omitted_names: Sequence[str],
    omitted_count: int | None = None,
) -> dict[str, Any]:
    block = dict(identity)
    if kept:
        block["registered_operations"] = [dict(row) for row in kept]
    if omitted_names:
        block["operations_omitted"] = [
            {"name": name, "reason": "view_budget"} for name in omitted_names
        ]
    count = len(omitted_names) if omitted_count is None else omitted_count
    if count:
        block["operations_omitted_count"] = count
    return block


def _fit_operation_index(
    payload: dict[str, Any],
    *,
    identity: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
) -> bool:
    kept: list[dict[str, Any]] = []
    omitted = len(rows)
    for row in rows:
        trial = list(kept) + [dict(row)]
        trial_omitted = len(rows) - len(trial)
        block = dict(identity)
        block["registered_operations"] = trial
        if trial_omitted:
            block["operations_omitted_count"] = trial_omitted
        trial_payload = dict(payload)
        trial_payload["operations"] = block
        if payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
            payload=trial_payload,
        ):
            kept, omitted = trial, trial_omitted
            continue
        break

    block = dict(identity)
    if kept:
        block["registered_operations"] = kept
    if omitted:
        block["operations_omitted_count"] = omitted
    if not block:
        return False
    return try_attach_value(
        payload,
        key="operations",
        value=block,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    )


def _compact_operation_row(row: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in (
        "name",
        "category",
        "compiler_support",
        "min_operands",
        "max_operands",
        "required_parameters",
        "optional_parameters",
    ):
        if key in row and row[key] is not None:
            out[key] = row[key]
    note = bound_text(row.get("compile_note"), field="compile_note")
    if note:
        out.update(note)
    desc = bound_text(row.get("description"), field="description")
    if desc:
        out.update(desc)
    params = row.get("parameters")
    if isinstance(params, list):
        compact_params: list[dict[str, Any]] = []
        for param in params:
            if not isinstance(param, Mapping):
                continue
            p_row = {
                key: param[key]
                for key in ("name", "param_type", "required", "default", "unit")
                if key in param and param[key] is not None
            }
            if "param_type" not in p_row and param.get("type") is not None:
                p_row["type"] = param.get("type")
            elif "param_type" in p_row:
                p_row["type"] = p_row.pop("param_type")
            p_desc = bound_text(param.get("description"), field="description")
            if p_desc:
                p_row.update(p_desc)
            if p_row:
                compact_params.append(p_row)
        if compact_params:
            out["parameters"] = compact_params
    return out


def _attach_schema_section(
    payload: dict[str, Any],
    *,
    outputs: Mapping[str, Any],
    section: str,
    models_key: str,
    identity_keys: Sequence[str],
) -> bool | None:
    present = any(key in outputs for key in (*identity_keys, models_key))
    if not present:
        return None
    identity = {key: outputs[key] for key in identity_keys if key in outputs}
    models = outputs.get(models_key)
    if not isinstance(models, Mapping) or not models:
        return try_attach_value(
            payload,
            key=section,
            value=identity,
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        )

    entries = [(name, value) for name, value in models.items()]
    kept: dict[str, Any] = {}
    omitted = len(entries)
    for name, value in entries:
        trial = dict(kept)
        trial[str(name)] = value
        trial_omitted = len(entries) - len(trial)
        block = dict(identity)
        block[models_key] = trial
        if trial_omitted:
            block["models_omitted_count"] = trial_omitted
        trial_payload = dict(payload)
        trial_payload[section] = block
        if payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES, payload=trial_payload
        ):
            kept, omitted = trial, trial_omitted
            continue
        break

    block = dict(identity)
    if kept:
        block[models_key] = kept
    if omitted:
        block["models_omitted_count"] = omitted
    return try_attach_value(
        payload,
        key=section,
        value=block,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    )


def _attach_examples(payload: dict[str, Any], raw: Any) -> bool | None:
    if not isinstance(raw, Mapping) or not raw:
        return None
    warning = raw.get("warning")
    identity: dict[str, Any] = {}
    if isinstance(warning, str) and warning.strip():
        identity["warning"] = warning.strip()

    named = {
        key: value
        for key, value in raw.items()
        if key != "warning" and value is not None
    }
    kept: dict[str, Any] = dict(identity)
    omitted: list[dict[str, Any]] = []
    for name, value in named.items():
        trial = dict(kept)
        trial[str(name)] = value
        trial_payload = dict(payload)
        trial_payload["examples"] = trial
        if omitted:
            trial_payload["examples"] = {
                **trial,
                "examples_omitted": list(omitted),
                "examples_omitted_count": len(omitted),
            }
        if payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES, payload=trial_payload
        ):
            kept = trial
            continue
        omitted.append({"example": str(name), "reason": "view_budget"})

    block = dict(kept)
    if omitted:
        block["examples_omitted"] = omitted
        block["examples_omitted_count"] = len(omitted)
    return try_attach_value(
        payload,
        key="examples",
        value=block,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    )


def _attach_validation_schema(payload: dict[str, Any], raw: Any) -> bool | None:
    if not isinstance(raw, Mapping) or not raw:
        return None
    if try_attach_value(
        payload,
        key="validation_schema",
        value=dict(raw),
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    ):
        return True

    identity = {
        key: raw[key]
        for key in ("$schema", "title", "type", "required", "properties")
        if key in raw
    }
    defs = raw.get("$defs") or raw.get("definitions")
    defs_key = (
        "$defs" if "$defs" in raw else "definitions" if "definitions" in raw else None
    )
    if not isinstance(defs, Mapping) or not defs_key:
        return try_attach_value(
            payload,
            key="validation_schema",
            value=identity,
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
        )

    kept: dict[str, Any] = {}
    entries = list(defs.items())
    omitted = len(entries)
    for name, value in entries:
        trial = dict(kept)
        trial[str(name)] = value
        trial_omitted = len(entries) - len(trial)
        block = dict(identity)
        block[defs_key] = trial
        if trial_omitted:
            block["definitions_omitted_count"] = trial_omitted
        trial_payload = dict(payload)
        trial_payload["validation_schema"] = block
        if payload_fits(
            schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES, payload=trial_payload
        ):
            kept, omitted = trial, trial_omitted
            continue
        break

    block = dict(identity)
    if kept:
        block[defs_key] = kept
    if omitted:
        block["definitions_omitted_count"] = omitted
    return try_attach_value(
        payload,
        key="validation_schema",
        value=block,
        schema_id=SCHEMA_DESCRIBE_FEATURE_GRAPH_CAPABILITIES,
    )
