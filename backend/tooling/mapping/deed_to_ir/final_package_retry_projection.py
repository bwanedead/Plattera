"""Retry shell projection for deed-to-IR final package prepare refusals."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .correction_contract_card import (
    CORRECTION_CONTRACT_REF,
    upstream_correction_row_contract_fields,
)

MAX_CANDIDATE_DELTAS = 8


def _copy_row_list(rows: Sequence[Any] | None) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    copied: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            copied.append(dict(row))
    return copied


def build_retry_package_shell(
    *,
    mapping_artifact_ref: str,
    expected_ir_artifact_ref: str,
    scope_results: Sequence[Any] | None,
    external_dependencies: Sequence[Any] | None,
    closure_dimensions: Sequence[Any] | None,
    notes: Sequence[Any] | None,
    correction_posture: Mapping[str, Any],
) -> dict[str, Any]:
    """Mechanical copyable retry shell — preserves package lineage; agent authors corrections."""
    contract_fields = upstream_correction_row_contract_fields()
    deltas = correction_posture.get("candidate_deltas")
    candidate_deltas: list[dict[str, Any]] = []
    if isinstance(deltas, list):
        for row in deltas[:MAX_CANDIDATE_DELTAS]:
            if isinstance(row, Mapping):
                candidate_deltas.append(dict(row))
    return {
        "mapping_artifact_ref": str(mapping_artifact_ref or "").strip(),
        "expected_ir_artifact_ref": str(expected_ir_artifact_ref or "").strip(),
        "scope_results": _copy_row_list(scope_results),
        "external_dependencies": _copy_row_list(external_dependencies),
        "closure_dimensions": _copy_row_list(closure_dimensions),
        "notes": _copy_row_list(notes),
        "missing_section": "upstream_corrections",
        "correction_contract_ref": CORRECTION_CONTRACT_REF,
        "candidate_deltas": candidate_deltas,
        "required_upstream_correction_fields": list(contract_fields.get("required_row_fields") or []),
        "optional_upstream_correction_fields": list(contract_fields.get("optional_row_fields") or []),
    }


def render_retry_package_shell_timeline_lines(
    shell: Mapping[str, Any] | None,
    *,
    indent: str = "  ",
) -> list[str]:
    if not isinstance(shell, Mapping) or not shell:
        return []
    lines = [f"{indent}retry_package_shell:"]
    mapping_ref = shell.get("mapping_artifact_ref")
    expected_ir = shell.get("expected_ir_artifact_ref")
    if mapping_ref:
        lines.append(f"{indent}  mapping_artifact_ref: {mapping_ref}")
    if expected_ir:
        lines.append(f"{indent}  expected_ir_artifact_ref: {expected_ir}")
    missing = shell.get("missing_section")
    if missing:
        lines.append(f"{indent}  missing_section: {missing}")
    contract_ref = shell.get("correction_contract_ref")
    if contract_ref:
        lines.append(f"{indent}  correction_contract_ref: {contract_ref}")
    deltas = shell.get("candidate_deltas")
    if isinstance(deltas, list):
        lines.append(f"{indent}  candidate_deltas: {len(deltas)}")
    for section in ("scope_results", "external_dependencies", "closure_dimensions", "notes"):
        rows = shell.get(section)
        if isinstance(rows, list) and rows:
            lines.append(f"{indent}  {section}_count: {len(rows)}")
    return lines
