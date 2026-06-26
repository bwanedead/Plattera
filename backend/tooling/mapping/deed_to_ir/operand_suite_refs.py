"""Canonical deed-to-IR operand suite artifact refs (path-free, run-scoped)."""

from __future__ import annotations

from .paths import UnsafeDeedToIrPathSegmentError, require_safe_path_segment

OPERAND_SUITE_REF = "deed_to_ir:operands"
OPERAND_SUITE_RUN_PREFIX = "deed_to_ir:operands:run:"
OPERAND_SUITE_WS_PREFIX = "deed_to_ir:operands:ws:"


def build_operand_suite_ref(
    *,
    run_id: str | None = None,
    workspace_id: str | None = None,
) -> str:
    """Return a scoped operand-suite ref for the current handoff context."""
    if run_id:
        return f"{OPERAND_SUITE_RUN_PREFIX}{_safe_ref_segment(run_id, field='run_id')}"
    if workspace_id:
        return f"{OPERAND_SUITE_WS_PREFIX}{_safe_ref_segment(workspace_id, field='workspace_id')}"
    return OPERAND_SUITE_REF


def parse_operand_suite_ref(ref_id: str) -> tuple[str, str | None]:
    """Parse ref kind and optional scope segment: canonical|run|ws|invalid."""
    text = str(ref_id or "").strip()
    if text == OPERAND_SUITE_REF:
        return "canonical", None
    if text.startswith(OPERAND_SUITE_RUN_PREFIX):
        segment = text[len(OPERAND_SUITE_RUN_PREFIX) :]
        return ("run", segment) if segment else ("invalid", None)
    if text.startswith(OPERAND_SUITE_WS_PREFIX):
        segment = text[len(OPERAND_SUITE_WS_PREFIX) :]
        return ("ws", segment) if segment else ("invalid", None)
    return "invalid", None


def validate_operand_suite_ref_access(
    ref_id: str,
    *,
    run_id: str | None,
    workspace_id: str | None,
) -> str | None:
    """Return error code when ref scope does not match handler context."""
    kind, segment = parse_operand_suite_ref(ref_id)
    if kind == "invalid":
        return "unsupported_operand_suite_ref"
    if kind == "canonical":
        return None
    if kind == "run":
        expected = build_operand_suite_ref(run_id=run_id)
        if ref_id != expected:
            return "operand_suite_ref_scope_mismatch"
        return None
    if kind == "ws":
        expected = build_operand_suite_ref(workspace_id=workspace_id)
        if ref_id != expected:
            return "operand_suite_ref_scope_mismatch"
        return None
    return "unsupported_operand_suite_ref"


def _safe_ref_segment(value: str, *, field: str) -> str:
    try:
        return require_safe_path_segment(value, field=field)
    except UnsafeDeedToIrPathSegmentError:
        cleaned = str(value or "").strip().replace("/", "_").replace("\\", "_")
        return cleaned[:64] or "unknown"
