"""Bounded mechanical excerpts of recent tool results for prompt transport.

The slice builder is a pure drop-only projection of stored
``kernel_step_result_records``. It selects the last ``max_records`` rows by
turn order and copies a handful of mechanical fields plus a bounded excerpt
of each row's ``outputs_for_continuity``. It does not inspect domain content
to decide inclusion, does not rank by semantic relevance, and does not embed
image or binary payloads.

The goal is to make the previous turn's tool output visible to the next LLM
turn without re-adding the raw record dump to default prompts.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from typing import Any

from .continuity_journal import CLIP_SENTINEL_KEY  # paired: see continuity_journal._clip_large_text_fields
from .point_crop_set_projection import project_point_crop_set_summary

DEFAULT_MAX_RECORDS = 3
DEFAULT_MAX_CHARS_PER_RESULT = 2500
DEFAULT_MAX_TOTAL_CHARS = 7000
DEFAULT_MAX_CHARS_PER_SLICE_ROW = 2500
_SLICE_ROW_METADATA_RESERVE = 160
_MAX_ARTIFACT_REFS = 16
_MAX_ARTIFACT_REF_CHARS = 128
_MAX_FIELD_SIGNALS_IN_SLICE = 8
_MAX_TEXT_SUMMARIES_IN_SLICE = 6
_MIN_TEXT_SUMMARY_CHARS_IN_SLICE = 120
_TIGHT_BUDGET_THRESHOLD = 220
_PRESERVE_NULL_SLICE_KEYS = frozenset(
    {
        "outputs_structural_metadata",
        "execution_reason_code",
        "latest_artifact_ref",
    }
)

# Text-field projection: per-field full-text cap and total lane cap.
# Fields below _TEXT_FIELD_MIN_LENGTH (status codes, short labels) are skipped.
# Fields at or below _TEXT_FIELD_FULL_CAP appear complete; larger fields get a
# bounded excerpt with explicit truncation markers.
_TEXT_FIELD_FULL_CAP: int = 12000
_TEXT_FIELD_LANE_CAP: int = 24000
_TEXT_FIELD_MIN_LENGTH: int = 60
_MAX_TEXT_FIELDS: int = 12
_TEXT_TRAVERSAL_DEPTH: int = 6
_MAX_LIST_ELEMENTS: int = 8  # max list elements to traverse for text projection

_BINARY_KEYS = frozenset(
    {
        "image_bytes",
        "image_b64",
        "image_base64",
        "image_evidence",
        "binary",
        "binary_payload",
        "pdf_bytes",
        "bytes",
        "raw_bytes",
    }
)


def _turn_index(row: Mapping[str, Any]) -> int | None:
    try:
        return int(row.get("kernel_turn_index"))
    except (TypeError, ValueError):
        return None


def _strip_binary(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_binary(inner)
            for key, inner in value.items()
            if str(key) not in _BINARY_KEYS
        }
    if isinstance(value, list):
        return [_strip_binary(item) for item in value]
    return value


# Root-level candidate keys to traverse when building structural metadata.
_ROOT_TRAVERSAL_CANDIDATES: tuple[str, ...] = (
    "result", "results", "data", "content", "payload",
    "outputs", "items", "records",
)
# Nested candidate keys used at depth > 0 (narrower set to avoid traversal explosion).
_NESTED_TRAVERSAL_CANDIDATES: tuple[str, ...] = (
    "payload", "data", "content", "result", "record", "items",
)
_MAX_TRAVERSAL_DEPTH: int = 4
_MAX_TRAVERSAL_PATHS: int = 10
_MAX_FIELD_SIGNALS: int = 16


def _collect_nested_keys(
    node: Mapping,
    out: dict[str, list[str]],
    *,
    path: str,
    depth: int,
) -> None:
    """Recursively collect key lists at each nesting level up to _MAX_TRAVERSAL_DEPTH.

    Path notation: top-level keys are stored under ``"top_level_keys"``;
    nested levels use ``"{path}_keys"`` — e.g. ``"results[0]_keys"``,
    ``"results[0].payload_keys"``, ``"results[0].payload.payload_keys"``.
    """
    if depth > _MAX_TRAVERSAL_DEPTH or len(out) >= _MAX_TRAVERSAL_PATHS:
        return
    label = "top_level_keys" if depth == 0 else f"{path}_keys"
    out[label] = [str(k) for k in node.keys()]
    if depth >= _MAX_TRAVERSAL_DEPTH:
        return
    candidates = _ROOT_TRAVERSAL_CANDIDATES if depth == 0 else _NESTED_TRAVERSAL_CANDIDATES
    for candidate in candidates:
        if len(out) >= _MAX_TRAVERSAL_PATHS:
            break
        child = node.get(candidate)
        if child is None:
            continue
        child_path = candidate if depth == 0 else f"{path}.{candidate}"
        # List shape: peek at the first Mapping element only
        if isinstance(child, (list, tuple)) and child and isinstance(child[0], Mapping):
            _collect_nested_keys(
                _strip_binary(child[0]),
                out,
                path=f"{child_path}[0]",
                depth=depth + 1,
            )
        elif isinstance(child, Mapping):
            _collect_nested_keys(
                _strip_binary(child),
                out,
                path=child_path,
                depth=depth + 1,
            )


def _field_signal(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str):
        return {
            "present": True,
            "value_type": "string",
            "non_empty": bool(value.strip()),
            "char_length": len(value),
            # is_complete: True when the full text fits within the prompt-visible cap,
            # i.e. text_field_summaries would show this field complete.
            "is_complete": len(value) <= _TEXT_FIELD_FULL_CAP,
        }
    if value is None:
        return {
            "present": True,
            "value_type": "null",
            "non_empty": False,
        }
    if isinstance(value, list):
        return {
            "present": True,
            "value_type": "list",
            "non_empty": bool(value),
            "item_count": len(value),
        }
    return None


def _collect_field_signals(
    node: Mapping,
    out: dict[str, dict[str, Any]],
    *,
    path: str,
    depth: int,
) -> None:
    """Collect bounded presence/non-empty signals for scalar and list fields."""
    if depth > _MAX_TRAVERSAL_DEPTH or len(out) >= _MAX_FIELD_SIGNALS:
        return
    for key, value in node.items():
        if len(out) >= _MAX_FIELD_SIGNALS:
            return
        key_text = str(key)
        child_path = key_text if depth == 0 else f"{path}.{key_text}"
        signal = _field_signal(value)
        if signal is not None:
            out[child_path] = signal
            if not (isinstance(value, (list, tuple)) and value and isinstance(value[0], Mapping)):
                continue
        if isinstance(value, Mapping):
            _collect_field_signals(
                _strip_binary(value),
                out,
                path=child_path,
                depth=depth + 1,
            )
            continue
        if isinstance(value, (list, tuple)) and value and isinstance(value[0], Mapping):
            _collect_field_signals(
                _strip_binary(value[0]),
                out,
                path=f"{child_path}[0]",
                depth=depth + 1,
            )


def _collect_text_fields(
    node: Any,
    summaries: list[dict[str, Any]],
    *,
    path: str,
    depth: int,
    lane_remaining: list[int],
) -> None:
    """Recursively collect text fields by dotted path for prompt-visible projection.

    Skips strings shorter than _TEXT_FIELD_MIN_LENGTH (status codes, labels).
    Fields at or below _TEXT_FIELD_FULL_CAP appear with is_complete=True and
    the full text.  Larger fields appear with is_complete=False plus a bounded
    excerpt and explicit truncation markers.  The lane_remaining list is a
    single-element mutable budget shared across the whole call tree.
    """
    if depth > _TEXT_TRAVERSAL_DEPTH or len(summaries) >= _MAX_TEXT_FIELDS:
        return
    if lane_remaining[0] <= 0:
        return

    if isinstance(node, str):
        length = len(node)
        if length < _TEXT_FIELD_MIN_LENGTH:
            return
        if length <= _TEXT_FIELD_FULL_CAP and length <= lane_remaining[0]:
            summaries.append({
                "path": path,
                "char_length": length,
                "is_complete": True,
                "text": node,
            })
            lane_remaining[0] -= length
        else:
            end = min(_TEXT_FIELD_FULL_CAP, lane_remaining[0])
            summaries.append({
                "path": path,
                "char_length": length,
                "is_complete": False,
                "excerpt_start": 0,
                "excerpt_end": end,
                "excerpt": node[:end],
                "truncation_reason": "prompt_projection_cap",
            })
            lane_remaining[0] -= end
        return

    if isinstance(node, Mapping):
        # Detect a clip sentinel emitted by _clip_large_text_fields in continuity_journal.
        # The original string was oversized and replaced with a structured marker carrying
        # the true original length.  Always emit is_complete=False so the agent knows the
        # text has been clipped at the storage layer, not just at the prompt-projection layer.
        if node.get(CLIP_SENTINEL_KEY) is True:
            orig_len = node.get("original_char_length") or 0
            excerpt = node.get("excerpt") or ""
            qualifying = (
                isinstance(excerpt, str)
                and (orig_len >= _TEXT_FIELD_MIN_LENGTH or len(excerpt) >= _TEXT_FIELD_MIN_LENGTH)
            )
            if qualifying and lane_remaining[0] > 0:
                visible_end = min(len(excerpt), _TEXT_FIELD_FULL_CAP, lane_remaining[0])
                summaries.append({
                    "path": path,
                    "char_length": int(orig_len),
                    "is_complete": False,
                    "excerpt_start": 0,
                    "excerpt_end": visible_end,
                    "excerpt": excerpt[:visible_end],
                    "truncation_reason": "continuity_storage_clip",
                })
                lane_remaining[0] -= visible_end
            return  # never recurse into the sentinel dict itself

        stripped = _strip_binary(node)
        for key, value in stripped.items():
            if len(summaries) >= _MAX_TEXT_FIELDS or lane_remaining[0] <= 0:
                break
            child_path = str(key) if not path else f"{path}.{key}"
            _collect_text_fields(
                value, summaries,
                path=child_path,
                depth=depth + 1,
                lane_remaining=lane_remaining,
            )
        return

    if isinstance(node, (list, tuple)) and node:
        # Traverse all elements within the lane/field budget so that peer artifacts
        # in a results list (results[1], results[2], …) are not silently hidden.
        for idx, item in enumerate(node[:_MAX_LIST_ELEMENTS]):
            if len(summaries) >= _MAX_TEXT_FIELDS or lane_remaining[0] <= 0:
                break
            child_path = f"{path}[{idx}]" if path else f"[{idx}]"
            _collect_text_fields(
                item, summaries,
                path=child_path,
                depth=depth + 1,
                lane_remaining=lane_remaining,
            )


def _extract_text_field_summaries(outputs: Any) -> list[dict[str, Any]] | None:
    """Extract meaningful text fields from outputs into a structured projection.

    Returns a list of summary dicts (one per text field >= _TEXT_FIELD_MIN_LENGTH),
    or None when outputs contains no qualifying text fields.  Each entry carries:
    - path: dotted field path from outputs root
    - char_length: full length of the source field
    - is_complete: True when the full text is included; False when truncated
    - text (complete) or excerpt/excerpt_start/excerpt_end/truncation_reason (incomplete)

    This projection is independent of the generic outputs_excerpt — it traverses
    the dict structure to find text regardless of JSON serialization order.
    """
    if not isinstance(outputs, Mapping):
        return None
    summaries: list[dict[str, Any]] = []
    lane_remaining = [_TEXT_FIELD_LANE_CAP]
    _collect_text_fields(outputs, summaries, path="", depth=0, lane_remaining=lane_remaining)
    return summaries if summaries else None


def _extract_structural_metadata(outputs: Any) -> dict[str, Any] | None:
    """Extract key sets at multiple nesting levels before truncation.

    Traverses list-of-results shapes generically to expose contract keys that
    would otherwise be hidden inside a truncated excerpt.  For example,
    ``outputs.results[0].payload.payload`` keys are visible even when the
    excerpt is cut before that depth.

    Bounded by _MAX_TRAVERSAL_DEPTH (4 levels) and _MAX_TRAVERSAL_PATHS (10
    entries) so the metadata stays compact regardless of artifact shape.

    Returns None when outputs is not a Mapping (e.g. a plain string result).
    """
    if not isinstance(outputs, Mapping):
        return None
    stripped = _strip_binary(outputs)
    if not isinstance(stripped, Mapping):
        return None
    meta: dict[str, Any] = {}
    _collect_nested_keys(stripped, meta, path="", depth=0)
    field_signals: dict[str, dict[str, Any]] = {}
    _collect_field_signals(stripped, field_signals, path="", depth=0)
    if field_signals:
        meta["field_signals"] = field_signals
    return meta or None


def check_outputs_excerpt_truncated(
    record: Mapping[str, Any],
    *,
    max_chars: int = DEFAULT_MAX_CHARS_PER_RESULT,
) -> bool:
    """Whether building a prompt slice for ``record`` would truncate the outputs excerpt.

    Applies the same bounded-excerpt projection used by the slice builder so
    that loop-health code can detect prompt-visible truncation independently of
    ``result_truncated`` (which reflects raw tool-output truncation, not
    prompt-excerpt truncation).
    """
    outputs = record.get("outputs_for_continuity", {})
    _, truncated = _bounded_outputs_excerpt(outputs, max_chars=max_chars)
    return truncated


def _bounded_outputs_excerpt(outputs: Any, *, max_chars: int) -> tuple[Any, bool]:
    """Return a bounded copy of outputs and whether it was truncated."""
    if isinstance(outputs, str):
        if len(outputs) <= max_chars:
            return outputs, False
        return outputs[:max_chars], True
    stripped = _strip_binary(outputs)
    try:
        blob = json.dumps(stripped, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        blob = str(stripped)
    if len(blob) <= max_chars:
        return stripped, False
    return blob[:max_chars], True


_MAX_RENDERED_EVIDENCE_REFS = 8
_MAX_DERIVED_REFS = 8


def _extract_evidence_artifact_summary(outputs: Any) -> dict[str, Any] | None:
    """Extract evidence artifact metadata from tool outputs without inspecting content.

    Covers two common evidence-producing result shapes:
    - ``render_evidence_locators`` results expose ``rendered_evidence_refs``
      (list of {source_ref, rendered_ref, locator_count, ...}).
    - ``transform_artifact`` results expose ``derived_ref_id`` and ``parent_ref_id``
      in ``outputs`` (the real tool output shape from artifact_transform.py).
      Also accepts the alias keys ``derived_ref`` / ``source_ref`` for forward
      compatibility with other tool shapes.

    Returns None when neither shape is detected. Purely structural — no domain
    content inspection.
    """
    if not isinstance(outputs, Mapping):
        return None
    summary: dict[str, Any] = {}

    # render_evidence_locators shape: outputs.rendered_evidence_refs
    rendered_refs = outputs.get("rendered_evidence_refs")
    if isinstance(rendered_refs, list) and rendered_refs:
        rendered_rows: list[dict[str, Any]] = []
        for row in rendered_refs[:_MAX_RENDERED_EVIDENCE_REFS]:
            if not isinstance(row, Mapping):
                continue
            rendered_rows.append({
                "source_ref": row.get("source_ref"),
                "rendered_ref": row.get("rendered_ref"),
                "locator_count": row.get("locator_count"),
                "summary_only_locator_count": row.get("summary_only_locator_count", 0),
                "unsupported_locator_count": row.get("unsupported_locator_count", 0),
            })
        if rendered_rows:
            summary["rendered_evidence_refs"] = rendered_rows

    # transform_artifact real output shape: outputs.derived_ref_id + outputs.parent_ref_id
    # (from tooling/mapping/transcript_edit/artifact_transform.py)
    derived_ref_id = outputs.get("derived_ref_id")
    if isinstance(derived_ref_id, str) and derived_ref_id.strip():
        summary["derived_ref"] = derived_ref_id  # normalise to canonical key for prompt
    parent_ref_id = outputs.get("parent_ref_id")
    if isinstance(parent_ref_id, str) and parent_ref_id.strip():
        summary["source_ref"] = parent_ref_id  # normalise to canonical key

    # Alias keys accepted for forward compatibility with other tool shapes
    if "derived_ref" not in summary:
        derived_ref = outputs.get("derived_ref")
        if isinstance(derived_ref, str) and derived_ref.strip():
            summary["derived_ref"] = derived_ref
    derived_refs = outputs.get("derived_refs")
    if isinstance(derived_refs, list) and derived_refs:
        summary["derived_refs"] = [str(r) for r in derived_refs[:_MAX_DERIVED_REFS] if r]
    # Also look one level deeper under common wrapper keys
    for wrapper_key in ("result", "data", "outputs"):
        child = outputs.get(wrapper_key)
        if not isinstance(child, Mapping):
            continue
        if "derived_ref" not in summary:
            child_derived = child.get("derived_ref_id") or child.get("derived_ref")
            if isinstance(child_derived, str) and child_derived.strip():
                summary["derived_ref"] = child_derived
        if "source_ref" not in summary:
            child_source = child.get("parent_ref_id") or child.get("source_ref")
            if isinstance(child_source, str) and child_source.strip():
                summary["source_ref"] = child_source

    # Top-level source_ref alias (some tool shapes)
    if "source_ref" not in summary:
        source_ref = outputs.get("source_ref")
        if isinstance(source_ref, str) and source_ref.strip():
            summary["source_ref"] = source_ref

    return summary if summary else None


def _extract_point_crop_set_summary(outputs: Any) -> dict[str, Any] | None:
    return project_point_crop_set_summary(outputs if isinstance(outputs, Mapping) else None)


def _extract_current_draft_ir_summary(outputs: Any) -> dict[str, Any] | None:
    from tooling.mapping.deed_to_ir.draft_ir_lifecycle import compact_current_draft_ir_for_projection

    if not isinstance(outputs, Mapping):
        return None
    current = outputs.get("current_draft_ir")
    if not isinstance(current, Mapping):
        return None
    return compact_current_draft_ir_for_projection(current)


def _extract_feature_graph_capabilities_summary(outputs: Any) -> dict[str, Any] | None:
    from tooling.mapping.deed_to_ir.read_action_projection import (
        compact_feature_graph_capabilities_summary,
    )

    if not isinstance(outputs, Mapping):
        return None
    return compact_feature_graph_capabilities_summary(outputs)


def _extract_first_draft_authoring_card(outputs: Any) -> dict[str, Any] | None:
    if not isinstance(outputs, Mapping):
        return None
    direct = outputs.get("first_draft_authoring_card")
    if isinstance(direct, Mapping):
        return dict(direct)
    starter = outputs.get("starter_contract")
    if isinstance(starter, Mapping):
        nested = starter.get("first_draft_authoring_card")
        if isinstance(nested, Mapping):
            return dict(nested)
    caps = _extract_feature_graph_capabilities_summary(outputs)
    if isinstance(caps, Mapping):
        card = caps.get("first_draft_authoring_card")
        if isinstance(card, Mapping):
            return dict(card)
        starter_summary = caps.get("starter_contract")
        if isinstance(starter_summary, Mapping):
            nested = starter_summary.get("first_draft_authoring_card")
            if isinstance(nested, Mapping):
                return dict(nested)
    return None


def _extract_mapping_review_summary(outputs: Any) -> dict[str, Any] | None:
    from tooling.mapping.deed_to_ir.mapping_review import compact_mapping_review_for_projection

    if not isinstance(outputs, Mapping):
        return None
    review = outputs.get("mapping_review")
    if isinstance(review, Mapping):
        return compact_mapping_review_for_projection(review)
    results = outputs.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, Mapping):
                continue
            nested = item.get("mapping_review")
            if isinstance(nested, Mapping):
                compact = compact_mapping_review_for_projection(nested)
                if compact is not None:
                    return compact
    return None


def _extract_mapping_operands_summary(outputs: Any) -> dict[str, Any] | None:
    from tooling.mapping.deed_to_ir.mapping_operands_projection import (
        compact_mapping_operands_for_projection,
    )

    if not isinstance(outputs, Mapping):
        return None
    for key in ("mapping_operands",):
        lane = outputs.get(key)
        if isinstance(lane, Mapping):
            compact = compact_mapping_operands_for_projection(lane)
            if compact is not None:
                return compact
    results = outputs.get("results")
    if isinstance(results, Mapping):
        lane = results.get("mapping_operands")
        if isinstance(lane, Mapping):
            return compact_mapping_operands_for_projection(lane)
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, Mapping):
                continue
            if item.get("artifact_type") == "deed_to_ir_operand_suite":
                compact = compact_mapping_operands_for_projection(item)
                if compact is not None:
                    return compact
    return compact_mapping_operands_for_projection(outputs)


def _extract_source_window_summary(outputs: Any) -> dict[str, Any] | None:
    from tooling.mapping.transcript_edit.source_window import compact_source_window_for_projection

    if not isinstance(outputs, Mapping):
        return None
    source_window = outputs.get("source_window")
    if not isinstance(source_window, Mapping):
        resolved = outputs.get("resolved_geometry")
        if isinstance(resolved, Mapping):
            source_window = resolved.get("source_window")
    return compact_source_window_for_projection(source_window if isinstance(source_window, Mapping) else None)


def _serialize_slice_row(slice_row: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            slice_row,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )
    except (TypeError, ValueError):
        return str(slice_row)


def _slice_row_char_length(slice_row: Mapping[str, Any]) -> int:
    return len(_serialize_slice_row(slice_row))


def _cap_structural_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metadata:
        return None
    capped = dict(metadata)
    field_signals = capped.get("field_signals")
    if isinstance(field_signals, dict) and len(field_signals) > _MAX_FIELD_SIGNALS_IN_SLICE:
        capped["field_signals"] = dict(list(field_signals.items())[:_MAX_FIELD_SIGNALS_IN_SLICE])
        capped["field_signals_truncated"] = True
    return capped


def _cap_text_field_summaries(summaries: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not summaries:
        return None
    if len(summaries) <= _MAX_TEXT_SUMMARIES_IN_SLICE:
        return summaries
    return summaries[:_MAX_TEXT_SUMMARIES_IN_SLICE]


def _clone_text_field_summaries(summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [dict(entry) for entry in summaries]


def _content_budget(max_row_chars: int) -> int:
    reserve = min(_SLICE_ROW_METADATA_RESERVE, max(0, max_row_chars // 3))
    return max(32, max_row_chars - reserve)


def _content_row_length(row: Mapping[str, Any]) -> int:
    return _slice_row_char_length(
        {key: value for key, value in row.items() if not str(key).startswith("slice_")}
    )


def _shrink_artifact_refs(slice_row: dict[str, Any]) -> bool:
    """Drop artifact ref lists to fit budget; never char-truncate copyable refs."""
    refs = slice_row.get("artifact_refs")
    if not isinstance(refs, list) or not refs:
        return False
    if slice_row.get("mapping_review") is not None:
        slice_row.pop("artifact_refs", None)
        slice_row.pop("latest_artifact_ref", None)
        slice_row["artifact_refs_omitted"] = int(slice_row.get("artifact_refs_omitted") or 0) + len(refs)
        return True
    if any(len(str(ref)) > _MAX_ARTIFACT_REF_CHARS for ref in refs):
        slice_row.pop("artifact_refs", None)
        slice_row.pop("latest_artifact_ref", None)
        slice_row["artifact_refs_omitted"] = int(slice_row.get("artifact_refs_omitted") or 0) + len(refs)
        return True
    if len(refs) > 1:
        slice_row["artifact_refs"] = refs[:-1]
        slice_row["artifact_refs_omitted"] = int(slice_row.get("artifact_refs_omitted") or 0) + 1
        slice_row["latest_artifact_ref"] = slice_row["artifact_refs"][0]
        return True
    return False


def _shrink_outputs_excerpt(slice_row: dict[str, Any]) -> bool:
    excerpt = slice_row.get("outputs_excerpt")
    if not isinstance(excerpt, str) or not excerpt:
        return False
    if len(excerpt) <= 64:
        return False
    new_len = max(64, int(len(excerpt) * 0.7))
    if new_len >= len(excerpt):
        return False
    slice_row["outputs_excerpt"] = excerpt[:new_len]
    slice_row["outputs_excerpt_truncated"] = True
    return True


def _compact_inert_slice_fields(
    slice_row: dict[str, Any],
    *,
    max_row_chars: int = DEFAULT_MAX_CHARS_PER_SLICE_ROW,
) -> bool:
    """Drop empty and false optional fields to reclaim row budget."""
    preserve_null = _PRESERVE_NULL_SLICE_KEYS if max_row_chars > _TIGHT_BUDGET_THRESHOLD else frozenset()
    changed = False
    for key in list(slice_row.keys()):
        if str(key).startswith("slice_"):
            continue
        value = slice_row[key]
        if value is None:
            if key in preserve_null:
                continue
            del slice_row[key]
            changed = True
            continue
        if key in {"result_truncated", "outputs_excerpt_truncated"} and value is False:
            del slice_row[key]
            changed = True
            continue
        if key == "artifact_refs" and isinstance(value, list) and not value:
            del slice_row[key]
            changed = True
            continue
        if key == "latest_artifact_ref" and not value:
            if key in preserve_null:
                continue
            del slice_row[key]
            changed = True
    return changed


def _drop_tight_budget_null_fields(slice_row: dict[str, Any], *, max_row_chars: int) -> bool:
    if max_row_chars > _TIGHT_BUDGET_THRESHOLD:
        return False
    changed = False
    for key in (
        "latest_artifact_ref",
        "execution_reason_code",
        "outputs_structural_metadata",
        "execution_state",
        "slice_original_char_length",
    ):
        if key in slice_row:
            del slice_row[key]
            changed = True
    trunc = str(slice_row.get("slice_truncation_reason") or "")
    if trunc and trunc != "budget":
        slice_row["slice_truncation_reason"] = "budget"
        changed = True
    return changed


def _shrink_text_field_summaries_in_place(
    slice_row: dict[str, Any],
    *,
    reasons: list[str],
) -> bool:
    summaries = slice_row.get("text_field_summaries")
    if not isinstance(summaries, list) or not summaries:
        return False
    changed = False
    for entry in summaries:
        if not isinstance(entry, dict):
            continue
        for key in ("text", "excerpt"):
            value = entry.get(key)
            if not isinstance(value, str) or len(value) <= _MIN_TEXT_SUMMARY_CHARS_IN_SLICE:
                continue
            new_len = max(_MIN_TEXT_SUMMARY_CHARS_IN_SLICE, int(len(value) * 0.7))
            if new_len < len(value):
                entry[key] = value[:new_len]
                entry["is_complete"] = False
                entry["truncation_reason"] = "slice_row_budget"
                changed = True
    if changed and "text_field_summaries_shortened" not in reasons:
        reasons.append("text_field_summaries_shortened")
    return changed


def _enforce_slice_row_budget(
    slice_row: dict[str, Any],
    *,
    max_row_chars: int,
    reasons: list[str],
) -> bool:
    """Mechanically shrink base row fields until the content fits ``max_row_chars``."""
    working_len = _slice_row_char_length(
        {key: value for key, value in slice_row.items() if key != "slice_char_length"}
    )
    if working_len <= max_row_chars:
        return False
    if slice_row.pop("slice_original_char_length", None) is not None:
        if "row_budget" not in reasons:
            reasons.append("row_budget")
        return True
    optional_keys = (
        "evidence_artifact_summary",
        "point_crop_set_summary",
        "source_window",
        "text_field_summaries",
    )
    if _shrink_artifact_refs(slice_row):
        if "artifact_refs_shortened" not in reasons:
            reasons.append("artifact_refs_shortened")
        return True
    if _shrink_outputs_excerpt(slice_row):
        if "outputs_excerpt" not in reasons:
            reasons.append("outputs_excerpt")
        return True
    if _shrink_text_field_summaries_in_place(slice_row, reasons=reasons):
        return True
    for key in optional_keys:
        if slice_row.pop(key, None) is not None:
            if "supplementary_metadata_dropped" not in reasons:
                reasons.append("supplementary_metadata_dropped")
            return True
    if slice_row.get("outputs_structural_metadata") is not None:
        slice_row["outputs_structural_metadata"] = None
        if "supplementary_metadata_dropped" not in reasons:
            reasons.append("supplementary_metadata_dropped")
        return True
    if _compact_inert_slice_fields(slice_row, max_row_chars=max_row_chars):
        return True
    reason_code = slice_row.get("execution_reason_code")
    if isinstance(reason_code, str) and len(reason_code) > 32:
        slice_row["execution_reason_code"] = reason_code[:32]
        return True
    return False


def _enforce_full_slice_row(
    slice_row: dict[str, Any],
    *,
    max_row_chars: int,
    reasons: list[str],
) -> None:
    """Shrink content and metadata until the fully serialized row fits."""
    for _ in range(256):
        slice_row.pop("slice_char_length", None)
        if _effective_row_length(slice_row) <= max_row_chars:
            return
        progressed = False
        while _enforce_slice_row_budget(
            slice_row,
            max_row_chars=max_row_chars,
            reasons=reasons,
        ):
            slice_row.pop("slice_char_length", None)
            progressed = True
            if _effective_row_length(slice_row) <= max_row_chars:
                return
        if _drop_tight_budget_null_fields(slice_row, max_row_chars=max_row_chars):
            progressed = True
            continue
        if _compact_inert_slice_fields(slice_row, max_row_chars=max_row_chars):
            progressed = True
            continue
        if slice_row.pop("slice_original_char_length", None) is not None:
            progressed = True
            continue
        summaries = slice_row.get("text_field_summaries")
        if isinstance(summaries, list) and summaries:
            if len(summaries) > 1:
                summaries.pop()
                if "text_field_summaries_dropped_entries" not in reasons:
                    reasons.append("text_field_summaries_dropped_entries")
                progressed = True
                continue
            if _shrink_text_field_summaries_in_place(slice_row, reasons=reasons):
                progressed = True
                continue
            slice_row.pop("text_field_summaries", None)
            if "text_field_summaries_dropped" not in reasons:
                reasons.append("text_field_summaries_dropped")
            progressed = True
            continue
        if slice_row.get("outputs_excerpt") not in ("", "{}"):
            slice_row["outputs_excerpt"] = "{}"
            slice_row["outputs_excerpt_truncated"] = True
            progressed = True
            continue
        if slice_row.get("artifact_refs"):
            slice_row["artifact_refs"] = []
            slice_row["latest_artifact_ref"] = None
            progressed = True
            continue
        for drop_key in (
            "slice_original_char_length",
            "execution_state",
            "execution_reason_code",
        ):
            if slice_row.pop(drop_key, None) is not None:
                progressed = True
                break
        if progressed:
            continue
        trunc = str(slice_row.get("slice_truncation_reason") or "")
        if trunc:
            compact = ",".join(part[:8] for part in trunc.split(",") if part)[:12]
            if compact != trunc:
                slice_row["slice_truncation_reason"] = compact or "budget"
                progressed = True
                continue
        if not progressed:
            break
    _compact_inert_slice_fields(slice_row, max_row_chars=max_row_chars)


def _row_fits_budget(row: Mapping[str, Any], *, max_row_chars: int) -> bool:
    return _content_row_length(row) <= max_row_chars


def _effective_row_length(slice_row: Mapping[str, Any]) -> int:
    """Estimate serialized row length including a self-consistent ``slice_char_length``."""
    if "slice_char_length" in slice_row:
        return _slice_row_char_length(slice_row)
    content_only = {
        key: value for key, value in slice_row.items() if key != "slice_char_length"
    }
    content_len = _slice_row_char_length(content_only)
    trial = dict(content_only)
    trial["slice_char_length"] = content_len
    return _slice_row_char_length(trial)


def _row_fits_full_budget(row: Mapping[str, Any], *, max_row_chars: int) -> bool:
    return _effective_row_length(row) <= max_row_chars


def _attach_slice_char_length(slice_row: dict[str, Any], *, max_row_chars: int) -> None:
    """Attach a self-consistent ``slice_char_length`` without exceeding the row budget."""
    for _ in range(16):
        slice_row.pop("slice_char_length", None)
        if _effective_row_length(slice_row) > max_row_chars:
            if _drop_tight_budget_null_fields(slice_row, max_row_chars=max_row_chars):
                continue
            for drop_key in ("execution_state",):
                if drop_key in slice_row:
                    del slice_row[drop_key]
                    break
            else:
                budget_reasons: list[str] = []
                existing = str(slice_row.get("slice_truncation_reason") or "").strip()
                if existing:
                    budget_reasons.append(existing)
                _enforce_full_slice_row(
                    slice_row,
                    max_row_chars=max_row_chars,
                    reasons=budget_reasons,
                )
            continue
        content_len = _slice_row_char_length(
            {key: value for key, value in slice_row.items() if key != "slice_char_length"}
        )
        slice_row["slice_char_length"] = content_len
        for _ in range(12):
            full_len = _slice_row_char_length(slice_row)
            if full_len <= max_row_chars:
                slice_row["slice_char_length"] = full_len
                if _slice_row_char_length(slice_row) == full_len:
                    return
            break
        break
    slice_row.pop("slice_char_length", None)
    slice_row["slice_char_length"] = min(
        max_row_chars,
        _slice_row_char_length(
            {key: value for key, value in slice_row.items() if key != "slice_char_length"}
        ),
    )


def _finalize_slice_row_metrics(
    slice_row: dict[str, Any],
    *,
    original_size: int,
    reasons: list[str],
    max_row_chars: int,
) -> dict[str, Any]:
    """Attach truncation metadata and an accurate self-inclusive slice_char_length."""
    content_size = _slice_row_char_length(
        {key: value for key, value in slice_row.items() if not key.startswith("slice_")}
    )
    if reasons or content_size < original_size:
        slice_row["slice_truncated"] = True
        slice_row["slice_truncation_reason"] = ",".join(dict.fromkeys(reasons)) if reasons else "row_budget"
        if original_size > content_size:
            slice_row["slice_original_char_length"] = original_size
    _enforce_full_slice_row(slice_row, max_row_chars=max_row_chars, reasons=reasons)
    if not _row_fits_full_budget(slice_row, max_row_chars=max_row_chars):
        slice_row["slice_truncated"] = True
        if not str(slice_row.get("slice_truncation_reason") or "").strip():
            slice_row["slice_truncation_reason"] = "budget"
        _enforce_full_slice_row(slice_row, max_row_chars=max_row_chars, reasons=reasons)
    _attach_slice_char_length(slice_row, max_row_chars=max_row_chars)
    for _ in range(8):
        if _effective_row_length(slice_row) <= max_row_chars:
            break
        _enforce_full_slice_row(slice_row, max_row_chars=max_row_chars, reasons=reasons)
        _attach_slice_char_length(slice_row, max_row_chars=max_row_chars)
    return slice_row


def _fit_text_field_summaries_to_row(
    summaries: list[dict[str, Any]] | None,
    *,
    base_row: Mapping[str, Any],
    max_row_chars: int,
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    """Shrink or drop text summaries so the combined row fits the budget."""
    if not summaries:
        return None, []
    reasons: list[str] = []
    working = _clone_text_field_summaries(summaries)

    def _trial(rows: list[dict[str, Any]]) -> dict[str, Any]:
        trial = dict(base_row)
        if rows:
            trial["text_field_summaries"] = rows
        return trial

    if _row_fits_budget(_trial(working), max_row_chars=max_row_chars):
        return working, reasons

    while working and not _row_fits_budget(_trial(working), max_row_chars=max_row_chars):
        shrunk_any = False
        for entry in working:
            for key in ("text", "excerpt"):
                value = entry.get(key)
                if not isinstance(value, str) or len(value) <= _MIN_TEXT_SUMMARY_CHARS_IN_SLICE:
                    continue
                new_len = max(_MIN_TEXT_SUMMARY_CHARS_IN_SLICE, int(len(value) * 0.7))
                if new_len < len(value):
                    entry[key] = value[:new_len]
                    entry["is_complete"] = False
                    entry["truncation_reason"] = "slice_row_budget"
                    shrunk_any = True
        if not shrunk_any:
            break
        if "text_field_summaries_shortened" not in reasons:
            reasons.append("text_field_summaries_shortened")

    while working and not _row_fits_budget(_trial(working), max_row_chars=max_row_chars):
        working.pop()
        if "text_field_summaries_dropped_entries" not in reasons:
            reasons.append("text_field_summaries_dropped_entries")
    if not working:
        return None, reasons + ["text_field_summaries_dropped"]

    if not _row_fits_budget(_trial(working), max_row_chars=max_row_chars):
        return None, reasons + ["text_field_summaries_dropped"]
    return working, reasons


def _build_bounded_slice_row(
    *,
    row: Mapping[str, Any],
    outputs: Any,
    max_row_chars: int,
    max_excerpt_chars: int,
) -> dict[str, Any]:
    text_field_summaries = _cap_text_field_summaries(_extract_text_field_summaries(outputs))
    evidence_artifact_summary = _extract_evidence_artifact_summary(outputs)
    point_crop_set_summary = _extract_point_crop_set_summary(outputs)
    current_draft_ir_summary = _extract_current_draft_ir_summary(outputs)
    mapping_review_summary = _extract_mapping_review_summary(outputs)
    mapping_operands_summary = _extract_mapping_operands_summary(outputs)
    first_draft_authoring_card = _extract_first_draft_authoring_card(outputs)
    feature_graph_capabilities_summary = _extract_feature_graph_capabilities_summary(outputs)
    if text_field_summaries:
        excerpt, excerpt_truncated = _bounded_outputs_excerpt(outputs, max_chars=256)
    elif (
        point_crop_set_summary is not None
        or evidence_artifact_summary is not None
        or current_draft_ir_summary is not None
        or mapping_review_summary is not None
        or mapping_operands_summary is not None
        or first_draft_authoring_card is not None
        or feature_graph_capabilities_summary is not None
    ):
        excerpt, excerpt_truncated = _bounded_outputs_excerpt(outputs, max_chars=256)
    else:
        excerpt, excerpt_truncated = _bounded_outputs_excerpt(outputs, max_chars=max_excerpt_chars)
    include_structural_metadata = (
        (excerpt_truncated or bool(row.get("result_truncated", False)))
        and point_crop_set_summary is None
        and evidence_artifact_summary is None
        and current_draft_ir_summary is None
        and mapping_review_summary is None
        and mapping_operands_summary is None
        and first_draft_authoring_card is None
        and feature_graph_capabilities_summary is None
        and not text_field_summaries
    )
    artifact_refs = row.get("artifact_refs") if isinstance(row.get("artifact_refs"), list) else []
    if mapping_review_summary is not None and artifact_refs:
        artifact_refs = []
    source_window_summary = _extract_source_window_summary(outputs)
    structural_metadata = (
        _cap_structural_metadata(_extract_structural_metadata(outputs))
        if include_structural_metadata
        else None
    )

    base: dict[str, Any] = {
        "kernel_turn_index": row.get("kernel_turn_index"),
        "action_type": row.get("action_type"),
        "execution_state": row.get("execution_state"),
        "execution_reason_code": row.get("execution_reason_code"),
        "result_truncated": bool(row.get("result_truncated", False)),
        "latest_artifact_ref": artifact_refs[0] if artifact_refs else None,
        "artifact_refs": artifact_refs,
        "outputs_excerpt": excerpt,
        "outputs_excerpt_truncated": bool(excerpt_truncated),
        "outputs_structural_metadata": structural_metadata,
    }
    if mapping_review_summary is not None:
        base["mapping_review"] = mapping_review_summary
    if mapping_operands_summary is not None:
        base["mapping_operands"] = mapping_operands_summary
    if first_draft_authoring_card is not None:
        base["first_draft_authoring_card"] = first_draft_authoring_card
    if feature_graph_capabilities_summary is not None:
        base["feature_graph_capabilities"] = feature_graph_capabilities_summary
    optional_fields: list[tuple[str, Any]] = []
    if point_crop_set_summary is not None:
        optional_fields.append(("point_crop_set_summary", point_crop_set_summary))
    if current_draft_ir_summary is not None:
        optional_fields.append(("current_draft_ir", current_draft_ir_summary))
    if evidence_artifact_summary is not None:
        optional_fields.append(("evidence_artifact_summary", evidence_artifact_summary))
    if source_window_summary is not None:
        optional_fields.append(("source_window", source_window_summary))

    slice_row = dict(base)
    dropped_supplementary: list[str] = []
    for key, value in optional_fields:
        trial = dict(slice_row)
        trial[key] = value
        if _row_fits_budget(trial, max_row_chars=max_row_chars):
            slice_row[key] = value
        else:
            dropped_supplementary.append(key)

    text_shrink_reasons: list[str] = []
    fitted_summaries: list[dict[str, Any]] | None = None
    if text_field_summaries is not None:
        fitted_summaries, text_shrink_reasons = _fit_text_field_summaries_to_row(
            text_field_summaries,
            base_row=slice_row,
            max_row_chars=max_row_chars,
        )
        if fitted_summaries is not None:
            slice_row["text_field_summaries"] = fitted_summaries

    excerpt_budget = max_excerpt_chars if not text_field_summaries else max(256, max_excerpt_chars)
    while not _row_fits_budget(slice_row, max_row_chars=max_row_chars) and excerpt_budget > 256:
        if text_field_summaries and excerpt_budget <= 256:
            break
        excerpt_budget = max(256, int(excerpt_budget * 0.7))
        excerpt, excerpt_truncated = _bounded_outputs_excerpt(outputs, max_chars=excerpt_budget)
        slice_row["outputs_excerpt"] = excerpt
        slice_row["outputs_excerpt_truncated"] = True
        if fitted_summaries is not None:
            fitted_summaries, extra_reasons = _fit_text_field_summaries_to_row(
                fitted_summaries,
                base_row=slice_row,
                max_row_chars=max_row_chars,
            )
            text_shrink_reasons.extend(extra_reasons)
            if fitted_summaries is not None:
                slice_row["text_field_summaries"] = fitted_summaries
            else:
                slice_row.pop("text_field_summaries", None)

    if not _row_fits_budget(slice_row, max_row_chars=max_row_chars):
        slice_row.pop("text_field_summaries", None)
        if "text_field_summaries_dropped" not in text_shrink_reasons:
            text_shrink_reasons.append("text_field_summaries_dropped")

    original_candidate = dict(base)
    for key, value in optional_fields:
        original_candidate[key] = value
    if text_field_summaries is not None:
        original_candidate["text_field_summaries"] = text_field_summaries
    original_size = _slice_row_char_length(original_candidate)

    reasons: list[str] = []
    if excerpt_truncated:
        reasons.append("outputs_excerpt")
    if dropped_supplementary:
        reasons.append("supplementary_metadata_dropped")
    reasons.extend(text_shrink_reasons)

    _enforce_slice_row_budget(slice_row, max_row_chars=max_row_chars, reasons=reasons)

    if text_field_summaries is not None and "text_field_summaries" not in slice_row:
        refitted, refit_reasons = _fit_text_field_summaries_to_row(
            text_field_summaries,
            base_row=slice_row,
            max_row_chars=max_row_chars,
        )
        if refitted is not None:
            slice_row["text_field_summaries"] = refitted
            reasons.extend(refit_reasons)

    return _finalize_slice_row_metrics(
        slice_row,
        original_size=original_size,
        reasons=reasons,
        max_row_chars=max_row_chars,
    )


def build_recent_tool_result_slices(
    step_result_records: list[dict[str, Any]],
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
    max_chars_per_result: int = DEFAULT_MAX_CHARS_PER_RESULT,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> list[dict[str, Any]]:
    """Mechanical bounded projection of the most recent tool-result rows.

    Selection is by ``kernel_turn_index`` order only. No semantic ranking.
    Binary/image payload keys are stripped. Each slice row is bounded as a whole
    so sibling results from the same turn are not crowded out by one oversized row.
    """
    if not step_result_records or max_records <= 0:
        return []
    max_row_chars = min(max_chars_per_result, DEFAULT_MAX_CHARS_PER_SLICE_ROW)
    rows: list[Mapping[str, Any]] = [
        row for row in step_result_records if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda r: _turn_index(r) if _turn_index(r) is not None else -1)
    kept = rows[-max_records:]

    slices: list[dict[str, Any]] = []
    total_chars = 0
    for row in reversed(kept):
        turn = _turn_index(row)
        if turn is None:
            continue
        outputs = row.get("outputs_for_continuity", {})
        raw_refs = row.get("artifact_refs") or []
        if isinstance(raw_refs, list):
            artifact_refs = [str(x) for x in raw_refs[:_MAX_ARTIFACT_REFS]]
        else:
            artifact_refs = []
        row_with_refs = dict(row)
        row_with_refs["artifact_refs"] = artifact_refs
        slice_row = _build_bounded_slice_row(
            row=row_with_refs,
            outputs=outputs,
            max_row_chars=max_row_chars,
            max_excerpt_chars=max_chars_per_result,
        )
        row_chars = int(slice_row.get("slice_char_length") or _slice_row_char_length(slice_row))
        if slices and total_chars + row_chars > max_total_chars:
            break
        slices.append(slice_row)
        total_chars += row_chars
    slices.reverse()
    return slices
