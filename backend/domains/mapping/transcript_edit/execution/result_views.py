"""Transcript-edit provider views for hydrate/transform action results.

Owns coherent, bounded AgentResultView payloads for continuity-critical tools.
Does not admit pending deliveries, touch prompts, or read/write dossier files.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import Any

from harness.execution.agent_result_view import (
    AgentResultView,
    AgentResultViewOmission,
    agent_result_view_omission_to_wire,
    agent_result_view_to_wire,
    build_agent_result_view,
)

SCHEMA_HYDRATE_ARTIFACT_REFS = "transcript_edit.hydrate_artifact_refs.v1"
SCHEMA_TRANSFORM_ARTIFACT = "transcript_edit.transform_artifact.v1"

MAX_HYDRATE_RESULT_ROWS = 32
MAX_HYDRATE_OMISSION_ROWS = 32
MAX_HYDRATE_ERROR_ROWS = 16
MAX_TRANSFORM_ANNOTATIONS = 16
MAX_TRANSFORM_LOCATOR_ROWS = 32
MAX_ERROR_MESSAGE_CHARS = 240
MAX_ERROR_CODE_CHARS = 128
MAX_ERROR_REF_ID_CHARS = 256

_HOST_OR_BINARY_KEYS = frozenset(
    {
        "absolute_path",
        "path",
        "b64",
        "image_b64",
        "base64",
        "bytes",
        "crop_img",
        "image",
        "image_obj",
    }
)
_COMMON_TRANSFORM_KEYS = (
    "sub_action",
    "derived_ref_id",
    "parent_ref_id",
    "basename",
    "width_height",
    "overlay_role",
    "factor_applied",
)
_LOCATOR_COLLECTION_KEYS = (
    "rendered_evidence_refs",
    "rendered_locators",
    "summary_only_locators",
    "unsupported_locators",
    "locator_summaries",
)


def attach_transcript_edit_result_view(
    result: Mapping[str, Any],
    *,
    action_id: str,
) -> dict[str, Any]:
    """Attach a hydrate/transform view or omission without altering other fields."""
    out = dict(result)
    if not _is_successful_action_result(out):
        return out
    outputs = out.get("outputs")
    if not isinstance(outputs, Mapping):
        return out

    view: AgentResultView | None = None
    omission: AgentResultViewOmission | None = None
    if action_id == "hydrate_artifact_refs":
        view, omission = build_hydrate_artifact_refs_view(outputs)
    elif action_id == "transform_artifact":
        view, omission = build_transform_artifact_view(outputs)
    else:
        return out

    if view is not None:
        out["agent_result_view"] = agent_result_view_to_wire(view)
        out.pop("agent_result_view_omitted", None)
    elif omission is not None:
        out["agent_result_view_omitted"] = agent_result_view_omission_to_wire(omission)
        out.pop("agent_result_view", None)
    return out


def wrap_handler_with_result_view(
    handler: Callable[[Any], Any],
    *,
    action_id: str,
) -> Callable[[Any], Any]:
    """Wrap a bound handler so successful results gain a provider view."""

    def wrapped(request: Any) -> Any:
        raw = handler(request)
        if not isinstance(raw, Mapping):
            return raw
        return attach_transcript_edit_result_view(raw, action_id=action_id)

    return wrapped


def build_hydrate_artifact_refs_view(
    outputs: Mapping[str, Any],
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Build a bounded hydrate view; never invents a continuity key."""
    sanitized_rows = [
        row
        for row in (_sanitize_hydrate_result_row(item) for item in list(outputs.get("results") or []))
        if row is not None
    ][:MAX_HYDRATE_RESULT_ROWS]
    error_rows = [
        row
        for row in (_sanitize_error_row(item) for item in list(outputs.get("errors") or []))
        if row is not None
    ]

    # Fit complete result rows first with an empty error collection so large
    # errors cannot evict valid hydrated content.
    kept: list[dict[str, Any]] = []
    omitted: list[dict[str, Any]] = []
    omitted_extra = 0
    for row in sanitized_rows:
        trial_kept = kept + [row]
        payload = _hydrate_payload(
            outputs,
            results=trial_kept,
            results_omitted=omitted,
            results_omitted_extra=omitted_extra,
            errors=[],
            errors_omitted_count=0,
        )
        view, _ = _try_hydrate_view(payload)
        if view is not None:
            kept = trial_kept
            continue
        desc = _hydrate_omission_descriptor(row)
        if desc is None:
            omitted_extra += 1
            continue
        trial_omitted = omitted + [desc]
        if len(trial_omitted) > MAX_HYDRATE_OMISSION_ROWS:
            omitted_extra += 1
            continue
        payload2 = _hydrate_payload(
            outputs,
            results=kept,
            results_omitted=trial_omitted,
            results_omitted_extra=omitted_extra,
            errors=[],
            errors_omitted_count=0,
        )
        view2, _ = _try_hydrate_view(payload2)
        if view2 is not None:
            omitted = trial_omitted
        else:
            omitted_extra += 1

    errors_kept, errors_omitted_count = _fit_error_rows(
        outputs,
        results=kept,
        results_omitted=omitted,
        results_omitted_extra=omitted_extra,
        error_rows=error_rows,
    )
    payload = _hydrate_payload(
        outputs,
        results=kept,
        results_omitted=omitted,
        results_omitted_extra=omitted_extra,
        errors=errors_kept,
        errors_omitted_count=errors_omitted_count,
    )
    return _try_hydrate_view(payload)


def build_transform_artifact_view(
    outputs: Mapping[str, Any],
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Build a bounded transform view; never invents a continuity key."""
    sub_action = str(outputs.get("sub_action") or "").strip()
    if sub_action == "render_evidence_locators":
        return _build_evidence_locator_transform_view(outputs)
    # Route point-crop transforms via the tooling projector (single ownership).
    from tooling.mapping.transcript_edit.point_crop_set_projection import (
        project_point_crop_set_summary,
    )

    crop_summary = project_point_crop_set_summary(outputs)
    if crop_summary is not None or sub_action.startswith("point_crops"):
        return _build_point_crop_transform_view(outputs, summary=crop_summary)
    return _build_generic_transform_view(outputs)


def _build_point_crop_transform_view(
    outputs: Mapping[str, Any],
    *,
    summary: Mapping[str, Any] | None = None,
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    if summary is None:
        return _try_transform_view(_common_transform_payload(outputs))

    points = list(summary.get("points") or []) if isinstance(summary.get("points"), list) else []
    kept_points = list(points)
    points_omitted_count = 0
    while True:
        payload = _common_transform_payload(outputs)
        crop_payload = _json_native(dict(summary))
        crop_payload["points"] = _json_native(kept_points)
        if points_omitted_count:
            crop_payload["points_omitted_count"] = points_omitted_count
        if points_omitted_count and isinstance(crop_payload.get("delegation_lines"), list):
            crop_payload["delegation_lines"] = crop_payload["delegation_lines"][: len(kept_points)]
        if points_omitted_count and isinstance(crop_payload.get("review_lines"), list):
            crop_payload["review_lines"] = crop_payload["review_lines"][: len(kept_points)]
        if points_omitted_count and isinstance(crop_payload.get("point_key_lines"), list):
            crop_payload["point_key_lines"] = crop_payload["point_key_lines"][: len(kept_points)]
        payload["point_crop_set"] = crop_payload
        view, omission = _try_transform_view(payload)
        if view is not None:
            return view, omission
        if not kept_points:
            return None, omission
        kept_points = kept_points[:-1]
        points_omitted_count = len(points) - len(kept_points)


def _build_evidence_locator_transform_view(
    outputs: Mapping[str, Any],
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    base = _common_transform_payload(outputs)
    collections: dict[str, list[dict[str, Any]]] = {}
    intake_omitted: dict[str, int] = {}
    for key in _LOCATOR_COLLECTION_KEYS:
        rows, omitted = _bound_mapping_rows(outputs.get(key), limit=MAX_TRANSFORM_LOCATOR_ROWS)
        collections[key] = rows
        intake_omitted[key] = omitted
    return _fit_transform_collections(
        base,
        collections,
        intake_omitted=intake_omitted,
    )


def _build_generic_transform_view(
    outputs: Mapping[str, Any],
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    base = _common_transform_payload(outputs)
    geometry = outputs.get("resolved_geometry")
    if isinstance(geometry, Mapping):
        compact_geo = _json_native(_strip_host_fields(dict(geometry)))
        if compact_geo:
            base["resolved_geometry"] = compact_geo
    source_window = outputs.get("source_window")
    if isinstance(source_window, Mapping):
        compact_sw = _json_native(_strip_host_fields(dict(source_window)))
        if compact_sw:
            base["source_window"] = compact_sw

    annotation_rows, intake_omitted = _bound_mapping_rows(
        outputs.get("resolved_annotations"),
        limit=MAX_TRANSFORM_ANNOTATIONS,
    )
    return _fit_transform_collections(
        base,
        {"resolved_annotations": annotation_rows},
        intake_omitted={"resolved_annotations": intake_omitted},
    )


def _fit_transform_collections(
    base_payload: Mapping[str, Any],
    collections: Mapping[str, Sequence[Mapping[str, Any]]],
    *,
    intake_omitted: Mapping[str, int] | None = None,
    omitted_key_suffix: str = "_omitted_count",
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    """Preserve identity first, then greedily keep complete collection rows that fit."""
    intake = {key: int(intake_omitted.get(key) or 0) for key in collections} if intake_omitted else {
        key: 0 for key in collections
    }
    kept: dict[str, list[dict[str, Any]]] = {key: [] for key in collections}
    # Start with all intake candidates omitted; reduce as rows are accepted.
    omitted_counts: dict[str, int] = {
        key: intake[key] + len(rows) for key, rows in collections.items()
    }

    for key, rows in collections.items():
        for row in rows:
            trial_kept = {k: list(v) for k, v in kept.items()}
            trial_kept[key] = list(kept[key]) + [dict(row)]
            trial_omitted = dict(omitted_counts)
            trial_omitted[key] = intake[key] + len(rows) - len(trial_kept[key])
            payload = _assemble_transform_payload(
                base_payload, trial_kept, trial_omitted, omitted_key_suffix
            )
            view, _ = _try_transform_view(payload)
            if view is not None:
                kept = trial_kept
                omitted_counts = trial_omitted
            # else: omit this whole row and continue with later rows

    payload = _assemble_transform_payload(base_payload, kept, omitted_counts, omitted_key_suffix)
    return _try_transform_view(payload)


def _assemble_transform_payload(
    base_payload: Mapping[str, Any],
    kept: Mapping[str, Sequence[Mapping[str, Any]]],
    omitted_counts: Mapping[str, int],
    omitted_key_suffix: str,
) -> dict[str, Any]:
    payload = dict(base_payload)
    for key, rows in kept.items():
        if rows:
            payload[key] = [dict(row) for row in rows]
        omitted = int(omitted_counts.get(key) or 0)
        if omitted:
            payload[f"{key}{omitted_key_suffix}"] = omitted
    return payload


def _common_transform_payload(outputs: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key in _COMMON_TRANSFORM_KEYS:
        value = outputs.get(key)
        if value in (None, "", [], (), {}):
            continue
        if key in _HOST_OR_BINARY_KEYS:
            continue
        payload[key] = _json_native(value)
    return payload


def _hydrate_payload(
    outputs: Mapping[str, Any],
    *,
    results: Sequence[Mapping[str, Any]],
    results_omitted: Sequence[Mapping[str, Any]],
    results_omitted_extra: int,
    errors: Sequence[Mapping[str, Any]],
    errors_omitted_count: int = 0,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "hydrated_count": int(outputs.get("hydrated_count") or 0)
        if _is_nonneg_int(outputs.get("hydrated_count"))
        else len(results),
        "cap_exceeded": bool(outputs.get("cap_exceeded"))
        if type(outputs.get("cap_exceeded")) is bool
        else False,
        "results": [_json_native(dict(row)) for row in results],
        "results_omitted_count": len(results_omitted) + max(0, results_omitted_extra),
    }
    if results_omitted:
        payload["results_omitted"] = [_json_native(dict(row)) for row in results_omitted]
    if errors:
        payload["errors"] = [_json_native(dict(row)) for row in errors]
    if errors_omitted_count:
        payload["errors_omitted_count"] = int(errors_omitted_count)
    return payload


def _fit_error_rows(
    outputs: Mapping[str, Any],
    *,
    results: Sequence[Mapping[str, Any]],
    results_omitted: Sequence[Mapping[str, Any]],
    results_omitted_extra: int,
    error_rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    kept: list[dict[str, Any]] = []
    omitted_count = 0
    for row in error_rows[:MAX_HYDRATE_ERROR_ROWS]:
        trial = kept + [row]
        payload = _hydrate_payload(
            outputs,
            results=results,
            results_omitted=results_omitted,
            results_omitted_extra=results_omitted_extra,
            errors=trial,
            errors_omitted_count=omitted_count,
        )
        view, _ = _try_hydrate_view(payload)
        if view is not None:
            kept = trial
        else:
            omitted_count += 1
    omitted_count += max(0, len(error_rows) - MAX_HYDRATE_ERROR_ROWS)
    return kept, omitted_count


def _sanitize_hydrate_result_row(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, Mapping):
        return None
    ref_id = raw.get("ref_id")
    kind = raw.get("kind")
    if not isinstance(ref_id, str) or not ref_id.strip():
        return None
    if not isinstance(kind, str) or not kind.strip():
        return None
    row: dict[str, Any] = {"ref_id": ref_id.strip(), "kind": kind.strip()}
    if kind.strip() == "t0_draft":
        text = raw.get("text")
        if isinstance(text, str):
            row["text"] = text
        metadata = raw.get("metadata")
        if isinstance(metadata, Mapping):
            compact_meta = _json_native(_strip_host_fields(dict(metadata)))
            if compact_meta:
                row["metadata"] = compact_meta
        return row
    if kind.strip() == "transcript_edit_draft":
        payload = raw.get("payload")
        if isinstance(payload, Mapping):
            row["payload"] = _json_native(_strip_host_fields(dict(payload)))
        return row
    if kind.strip() in {"source_image", "derived_image"}:
        for key in (
            "basename",
            "role",
            "exists",
            "size_bytes",
            "width_height",
            "parent_ref_id",
            "sub_action",
            "representation_kind",
            "content_identity_posture",
            "source_identity_posture",
            "lineage_depth",
        ):
            value = raw.get(key)
            if value not in (None, "", [], (), {}):
                row[key] = _json_native(value)
        return row
    for key, value in raw.items():
        if key in {"ref_id", "kind"} or key in _HOST_OR_BINARY_KEYS:
            continue
        if isinstance(value, (str, bool, int, float)) or isinstance(value, (list, tuple, dict)):
            sanitized = _json_native(_strip_host_value(value))
            if sanitized not in (None, "", [], {}):
                row[key] = sanitized
    return row


def _hydrate_omission_descriptor(row: Mapping[str, Any]) -> dict[str, Any] | None:
    ref_id = row.get("ref_id")
    kind = row.get("kind")
    if not isinstance(ref_id, str) or not ref_id.strip():
        return None
    if not isinstance(kind, str) or not kind.strip():
        return None
    return {"ref_id": ref_id.strip(), "kind": kind.strip(), "reason": "view_budget"}


def _sanitize_error_row(raw: Any) -> dict[str, Any] | None:
    """Sanitize one error row. Oversized code/ref_id fields are omitted whole."""
    if not isinstance(raw, Mapping):
        return None
    row: dict[str, Any] = {}
    code = raw.get("code") or raw.get("reason_code")
    if isinstance(code, str) and code.strip():
        text = code.strip()
        if len(text) <= MAX_ERROR_CODE_CHARS:
            row["code"] = text
        else:
            row["code_omitted"] = True
            row["code_chars"] = len(text)
    ref_id = raw.get("ref_id")
    if isinstance(ref_id, str) and ref_id.strip():
        text = ref_id.strip()
        if len(text) <= MAX_ERROR_REF_ID_CHARS:
            row["ref_id"] = text
        else:
            row["ref_id_omitted"] = True
            row["ref_id_chars"] = len(text)
    message = raw.get("message")
    if isinstance(message, str) and message.strip():
        if len(message) <= MAX_ERROR_MESSAGE_CHARS:
            row["message"] = message
        else:
            row["message_omitted"] = True
            row["message_chars"] = len(message)
    return row or None


def _bound_mapping_rows(raw: Any, *, limit: int) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(raw, list):
        return [], 0
    kept: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        kept.append(_json_native(_strip_host_fields(dict(item))))
        if len(kept) >= limit:
            break
    omitted = max(0, len([x for x in raw if isinstance(x, Mapping)]) - len(kept))
    return kept, omitted


def _strip_host_fields(value: MutableMapping[str, Any] | dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        if str(key) in _HOST_OR_BINARY_KEYS:
            continue
        stripped = _strip_host_value(item)
        if stripped in (None, "", [], {}):
            continue
        out[str(key)] = stripped
    return out


def _strip_host_value(value: Any) -> Any:
    """Recursively strip host/binary keys from mappings nested in objects or lists."""
    if isinstance(value, Mapping):
        return _strip_host_fields(dict(value))
    if isinstance(value, (list, tuple)):
        return [_strip_host_value(item) for item in value]
    return value


def _json_native(value: Any) -> Any:
    """Convert tuple wire arrays to lists recursively for BR-016 JSON-native views.

    Does not mutate caller inputs and does not stringify unsupported objects.
    """
    if isinstance(value, tuple):
        return [_json_native(item) for item in value]
    if isinstance(value, list):
        return [_json_native(item) for item in value]
    if isinstance(value, Mapping):
        return {str(k): _json_native(v) for k, v in value.items()}
    return value


def _try_hydrate_view(
    payload: Mapping[str, Any],
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    return build_agent_result_view(
        schema_id=SCHEMA_HYDRATE_ARTIFACT_REFS,
        payload=_json_native(dict(payload)),
    )


def _try_transform_view(
    payload: Mapping[str, Any],
) -> tuple[AgentResultView | None, AgentResultViewOmission | None]:
    return build_agent_result_view(
        schema_id=SCHEMA_TRANSFORM_ARTIFACT,
        payload=_json_native(dict(payload)),
    )


def _is_successful_action_result(result: Mapping[str, Any]) -> bool:
    if result.get("executed") is not True:
        return False
    if result.get("refusal") is not None:
        return False
    return True


def _is_nonneg_int(value: Any) -> bool:
    return type(value) is int and value >= 0
