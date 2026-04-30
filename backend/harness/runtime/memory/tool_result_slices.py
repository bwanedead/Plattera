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
    for row in kept:
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
    return slices
