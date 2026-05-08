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
from collections.abc import Mapping
from typing import Any

DEFAULT_MAX_RECORDS = 3
DEFAULT_MAX_CHARS_PER_RESULT = 2500
DEFAULT_MAX_TOTAL_CHARS = 7000
_MAX_ARTIFACT_REFS = 16

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


def build_recent_tool_result_slices(
    step_result_records: list[dict[str, Any]],
    *,
    max_records: int = DEFAULT_MAX_RECORDS,
    max_chars_per_result: int = DEFAULT_MAX_CHARS_PER_RESULT,
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> list[dict[str, Any]]:
    """Mechanical bounded projection of the most recent tool-result rows.

    Selection is by ``kernel_turn_index`` order only. No semantic ranking.
    Binary/image payload keys are stripped. Each slice is bounded in size
    and the total lane is bounded by ``max_total_chars``.

    Rows are processed newest-first so the most recent result is always
    included regardless of budget.  Older results are included while budget
    remains.  The returned list is in chronological (ascending turn) order.

    ``evidence_artifact_summary`` is included whenever the outputs contain
    evidence artifact fields (rendered_evidence_refs, derived_ref, source_ref).
    This is always included when present so the next prompt turn can see what
    focused evidence was produced without requiring re-hydration.
    """
    if not step_result_records or max_records <= 0:
        return []
    rows: list[Mapping[str, Any]] = [
        row for row in step_result_records if isinstance(row, Mapping)
    ]
    rows.sort(key=lambda r: _turn_index(r) if _turn_index(r) is not None else -1)
    kept = rows[-max_records:]

    slices: list[dict[str, Any]] = []
    total_chars = 0
    for row in reversed(kept):  # newest-first so newest is always admitted
        turn = _turn_index(row)
        if turn is None:
            continue
        outputs = row.get("outputs_for_continuity", {})
        excerpt, excerpt_truncated = _bounded_outputs_excerpt(
            outputs, max_chars=max_chars_per_result
        )
        include_structural_metadata = excerpt_truncated or bool(
            row.get("result_truncated", False)
        )
        raw_refs = row.get("artifact_refs") or []
        if isinstance(raw_refs, list):
            artifact_refs = [str(x) for x in raw_refs[:_MAX_ARTIFACT_REFS]]
        else:
            artifact_refs = []
        evidence_artifact_summary = _extract_evidence_artifact_summary(outputs)
        text_field_summaries = _extract_text_field_summaries(outputs)
        slice_row: dict[str, Any] = {
            "kernel_turn_index": turn,
            "action_type": row.get("action_type"),
            "execution_state": row.get("execution_state"),
            "execution_reason_code": row.get("execution_reason_code"),
            "result_truncated": bool(row.get("result_truncated", False)),
            "latest_artifact_ref": artifact_refs[0] if artifact_refs else None,
            "artifact_refs": artifact_refs,
            "outputs_excerpt": excerpt,
            "outputs_excerpt_truncated": bool(excerpt_truncated),
            "outputs_structural_metadata": (
                _extract_structural_metadata(outputs)
                if include_structural_metadata
                else None
            ),
        }
        if evidence_artifact_summary is not None:
            slice_row["evidence_artifact_summary"] = evidence_artifact_summary
        if text_field_summaries is not None:
            slice_row["text_field_summaries"] = text_field_summaries
        try:
            row_chars = len(
                json.dumps(slice_row, ensure_ascii=False, default=str)
            )
        except (TypeError, ValueError):
            row_chars = max_chars_per_result
        if slices and total_chars + row_chars > max_total_chars:
            break
        slices.append(slice_row)
        total_chars += row_chars
    slices.reverse()  # restore chronological (ascending turn) order
    return slices
