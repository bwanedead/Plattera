"""Deed-to-IR finalizer AgentResultView builder (post-boundary public results only)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from tooling.mapping.deed_to_ir.finalization_session import (
    STATUS_PENDING_DECISIONS,
    STATUS_PREVIEW_READY,
    STATUS_PUBLISHED,
    compact_finalization_session_for_prompt,
)

from .result_view_common import (
    bound_message,
    copy_scalar_fields,
    try_build_view,
    view_budget_omission,
)

SCHEMA_FINALIZE_CURRENT_OUTPUT = "deed_to_ir.finalize_current_output.v1"

# Explicit allowlist only — never select legacy cards or prompt_carry_forward.
_FINALIZER_SCALAR_KEYS = (
    "finalization_status",
    "final_package_preview_ref",
    "output_revision_ref",
    "mapping_artifact_ref",
    "ir_artifact_ref",
    "next_required_action",
    "expected_next",
    "idempotent_replay",
    "repair_hint",
)


def build_finalize_current_output_view(
    result: Mapping[str, Any],
    *,
    continuity_key: str | None,
):
    """Build from an already-normalized public finalizer result (success or refusal)."""
    outputs = result.get("outputs")
    if not isinstance(outputs, Mapping):
        outputs = {}

    base = copy_scalar_fields(outputs, _FINALIZER_SCALAR_KEYS)

    refusal = result.get("refusal")
    if isinstance(refusal, Mapping):
        reason = refusal.get("reason_code")
        if isinstance(reason, str) and reason.strip():
            base["refusal_reason_code"] = reason.strip()
        if type(refusal.get("retryable")) is bool:
            base["refusal_retryable"] = refusal["retryable"]

    # Exact missing IDs once at top level (not repeated inside the session summary).
    missing = outputs.get("missing")
    if isinstance(missing, Mapping) and missing:
        base["missing"] = {
            key: list(value) if isinstance(value, list) else value
            for key, value in missing.items()
        }

    lineage = outputs.get("current_mapping_lineage")
    if isinstance(lineage, Mapping) and lineage:
        base["current_mapping_lineage"] = dict(lineage)

    error = outputs.get("error")
    if isinstance(error, Mapping):
        code = error.get("code")
        if isinstance(code, str) and code.strip():
            base["error_code"] = code.strip()
        msg = bound_message(error.get("message"))
        if msg:
            base.update(msg)

    session_summary = build_finalization_session_result_view_summary(
        outputs.get("active_finalization_session")
        if isinstance(outputs.get("active_finalization_session"), Mapping)
        else None
    )

    if session_summary is not None:
        session, markers = resolve_session_summary_for_envelope(
            session_summary,
            fits=lambda candidate: try_build_view(
                schema_id=SCHEMA_FINALIZE_CURRENT_OUTPUT,
                payload={**base, "active_finalization_session": candidate},
                continuity_key=continuity_key,
            )[0]
            is not None,
        )
        payload = dict(base)
        payload.update(markers)
        if session is not None:
            payload["active_finalization_session"] = session
        return try_build_view(
            schema_id=SCHEMA_FINALIZE_CURRENT_OUTPUT,
            payload=payload,
            continuity_key=continuity_key,
        )

    return try_build_view(
        schema_id=SCHEMA_FINALIZE_CURRENT_OUTPUT,
        payload=base,
        continuity_key=continuity_key,
    )


def build_finalization_session_result_view_summary(
    session: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Result-view session summary: no duplicated requirement/missing ID lists."""
    compact = compact_finalization_session_for_prompt(session)
    if compact is None:
        return None

    status = str(compact.get("status") or "").strip()
    if status in {STATUS_PREVIEW_READY, STATUS_PUBLISHED}:
        return dict(compact)

    if status != STATUS_PENDING_DECISIONS:
        return None

    summary: dict[str, Any] = {"status": STATUS_PENDING_DECISIONS}
    lineage = compact.get("lineage")
    if isinstance(lineage, Mapping) and lineage:
        summary["lineage"] = dict(lineage)
    allowed = compact.get("allowed_values")
    if isinstance(allowed, Mapping) and allowed:
        summary["allowed_values"] = dict(allowed)

    requirements = compact.get("requirements") if isinstance(compact.get("requirements"), Mapping) else {}
    summary["requirement_counts"] = {
        "scope_ids": len(requirements.get("scope_ids") or []),
        "correction_ids": len(requirements.get("correction_ids") or []),
        "dependency_ids": len(requirements.get("dependency_ids") or []),
    }

    decisions = compact.get("decisions")
    if isinstance(decisions, Mapping) and decisions:
        summary["decisions"] = dict(decisions)

    diagnostics = compact.get("diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        summary["diagnostics"] = list(diagnostics)

    return summary


def resolve_session_summary_for_envelope(
    session_summary: Mapping[str, Any],
    *,
    fits: Callable[[Mapping[str, Any]], bool],
) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """Keep session core under pressure; drop diagnostics before the whole session.

    Returns ``(session_or_none, payload_markers)``.
    """
    summary = dict(session_summary)
    if fits(summary):
        return summary, {}

    diagnostics = summary.get("diagnostics")
    if isinstance(diagnostics, list) and diagnostics:
        core = {key: value for key, value in summary.items() if key != "diagnostics"}
        core["diagnostics_omitted_count"] = len(diagnostics)
        core["diagnostics_omitted"] = view_budget_omission(fields=["diagnostics"])
        if fits(core):
            return core, {}

    return None, {
        "active_finalization_session_omitted": view_budget_omission(
            fields=["active_finalization_session"]
        )
    }
