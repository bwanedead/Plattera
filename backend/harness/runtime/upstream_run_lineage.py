"""Mechanical upstream run lineage for cross-run audit/UI stitching.

Generic harness contract only — no domain imports, no upstream existence checks,
and no semantic interpretation of relations or handoff refs.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

UPSTREAM_RUN_LINEAGE_LAUNCH_KEY = "upstream_run_lineage"
UPSTREAM_RUN_LINEAGE_SCHEMA_VERSION = "upstream_run_lineage.v1"

MAX_UPSTREAM_RUN_ROWS = 8
MAX_HANDOFF_REFS_PER_ROW = 32
MAX_RUN_ID_LENGTH = 128
MAX_DOMAIN_ID_LENGTH = 64
MAX_RELATION_LENGTH = 64
MAX_HANDOFF_REF_LENGTH = 1024

_UPSTREAM_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_DOMAIN_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")
_RELATION_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


class UpstreamRunLineageError(ValueError):
    """Raised when upstream run lineage shape or bounds are invalid."""


def partition_launch_context_for_upstream_lineage(
    launch_context: Mapping[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Extract normalized lineage and return adapter/prompt-safe launch context."""
    if UPSTREAM_RUN_LINEAGE_LAUNCH_KEY not in launch_context:
        return None, dict(launch_context)
    raw = launch_context.get(UPSTREAM_RUN_LINEAGE_LAUNCH_KEY)
    normalized = normalize_upstream_run_lineage(raw)
    domain_context = {
        key: value
        for key, value in launch_context.items()
        if str(key) != UPSTREAM_RUN_LINEAGE_LAUNCH_KEY
    }
    return normalized, domain_context


def normalize_upstream_run_lineage(raw: Any) -> dict[str, Any]:
    """Mechanically normalize authored upstream lineage; preserve exact field values."""
    if not isinstance(raw, Mapping):
        raise UpstreamRunLineageError("upstream_run_lineage_not_object")

    schema_version = _require_exact_text(
        raw.get("schema_version"),
        field="schema_version",
        max_length=64,
    )
    if schema_version != UPSTREAM_RUN_LINEAGE_SCHEMA_VERSION:
        raise UpstreamRunLineageError("upstream_run_lineage_schema_version_invalid")

    upstream_runs_raw = raw.get("upstream_runs")
    if not isinstance(upstream_runs_raw, list):
        raise UpstreamRunLineageError("upstream_run_lineage_upstream_runs_not_list")
    if not upstream_runs_raw:
        raise UpstreamRunLineageError("upstream_run_lineage_upstream_runs_empty")
    if len(upstream_runs_raw) > MAX_UPSTREAM_RUN_ROWS:
        raise UpstreamRunLineageError("upstream_run_lineage_upstream_runs_too_many")

    upstream_runs: list[dict[str, Any]] = []
    for row in upstream_runs_raw:
        if not isinstance(row, Mapping):
            raise UpstreamRunLineageError("upstream_run_lineage_row_not_object")
        upstream_runs.append(_normalize_upstream_run_row(row))

    return {
        "schema_version": schema_version,
        "upstream_runs": upstream_runs,
    }


def _normalize_upstream_run_row(row: Mapping[str, Any]) -> dict[str, Any]:
    run_id = _require_upstream_run_id(row.get("run_id"))
    domain_id = _require_domain_id(row.get("domain_id"))
    relation = _require_relation(row.get("relation"))
    handoff_refs = _normalize_handoff_refs(row.get("handoff_refs"))
    return {
        "run_id": run_id,
        "domain_id": domain_id,
        "relation": relation,
        "handoff_refs": handoff_refs,
    }


def _normalize_handoff_refs(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        raise UpstreamRunLineageError("upstream_run_lineage_handoff_refs_not_list")
    if not raw:
        raise UpstreamRunLineageError("upstream_run_lineage_handoff_refs_empty")
    if len(raw) > MAX_HANDOFF_REFS_PER_ROW:
        raise UpstreamRunLineageError("upstream_run_lineage_handoff_refs_too_many")

    refs: list[str] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise UpstreamRunLineageError("upstream_run_lineage_handoff_ref_not_string")
        text = entry.strip()
        if not text:
            raise UpstreamRunLineageError("upstream_run_lineage_handoff_ref_empty")
        if len(text) > MAX_HANDOFF_REF_LENGTH:
            raise UpstreamRunLineageError("upstream_run_lineage_handoff_ref_too_long")
        _require_handoff_ref_render_safe(text)
        refs.append(text)
    return refs


def _require_handoff_ref_render_safe(text: str) -> None:
    """Handoff refs are opaque identifiers; reject only render-breaking control chars."""
    if any(ord(ch) < 32 for ch in text):
        raise UpstreamRunLineageError("upstream_run_lineage_handoff_ref_control_character")
    if "`" in text:
        raise UpstreamRunLineageError("upstream_run_lineage_handoff_ref_unrenderable")


def _require_upstream_run_id(value: Any) -> str:
    text = _require_exact_text(value, field="run_id", max_length=MAX_RUN_ID_LENGTH)
    if not _UPSTREAM_RUN_ID_PATTERN.fullmatch(text):
        raise UpstreamRunLineageError("upstream_run_lineage_run_id_unsafe")
    return text


def _require_domain_id(value: Any) -> str:
    text = _require_exact_text(value, field="domain_id", max_length=MAX_DOMAIN_ID_LENGTH)
    if not _DOMAIN_ID_PATTERN.fullmatch(text):
        raise UpstreamRunLineageError("upstream_run_lineage_domain_id_unsafe")
    return text


def _require_relation(value: Any) -> str:
    text = _require_exact_text(value, field="relation", max_length=MAX_RELATION_LENGTH)
    if not _RELATION_PATTERN.fullmatch(text):
        raise UpstreamRunLineageError("upstream_run_lineage_relation_unsafe")
    return text


def _require_exact_text(value: Any, *, field: str, max_length: int) -> str:
    if not isinstance(value, str):
        raise UpstreamRunLineageError(f"upstream_run_lineage_{field}_not_string")
    if value != value.strip():
        raise UpstreamRunLineageError(f"upstream_run_lineage_{field}_not_trimmed")
    if not value:
        raise UpstreamRunLineageError(f"upstream_run_lineage_{field}_empty")
    if len(value) > max_length:
        raise UpstreamRunLineageError(f"upstream_run_lineage_{field}_too_long")
    return value
