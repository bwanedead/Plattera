"""Startup context block for deed-to-IR from transcript-edit handoff."""

from __future__ import annotations

from domains.prompting import PromptBlock

from ..branch import DEED_TO_IR_DOMAIN_ID
from ...payloads import DeedToIrStartupHandoff

DEED_TO_IR_STARTUP_CONTEXT_VERSION = "v2"
_STARTUP_CONTEXT_SOURCE_PATH = (
    "backend/domains/mapping/deed_to_ir/prompting/surfaces/startup_context.py"
)


def build_startup_context_block(handoff: DeedToIrStartupHandoff) -> PromptBlock:
    return PromptBlock(
        block_id="deed_to_ir_startup_context",
        layer="domain_startup_context",
        owner=DEED_TO_IR_DOMAIN_ID,
        source_path=_STARTUP_CONTEXT_SOURCE_PATH,
        version=DEED_TO_IR_STARTUP_CONTEXT_VERSION,
        text=_format_startup_context(handoff),
    )


def _format_startup_context(handoff: DeedToIrStartupHandoff) -> str:
    lines: list[str] = [
        "## Deed-to-IR Startup Handoff",
        "",
        "Mechanical summary of transcript-edit final output lanes. "
        "This is orientation memory from upstream — not earned IR, closure, or compile truth.",
        "",
        "### Scope",
        f"- dossier_id: `{handoff.scope.dossier_id}`",
    ]
    if handoff.scope.run_id:
        lines.append(f"- run_id: `{handoff.scope.run_id}`")
    if handoff.scope.workspace_id:
        lines.append(f"- workspace_id: `{handoff.scope.workspace_id}`")
    if handoff.scope.transcription_id:
        lines.append(f"- transcription_id: `{handoff.scope.transcription_id}`")
    lines.append("")

    lines.append("### Transcript-edit source")
    if handoff.source.loaded_source_label:
        lines.append(f"- loaded_from: `{handoff.source.loaded_source_label}`")
    if handoff.source.source_revision_ref:
        lines.append(f"- source_revision_ref: `{handoff.source.source_revision_ref}`")
    if handoff.source.published_at:
        lines.append(f"- published_at: {handoff.source.published_at}")
    lines.append("")

    if handoff.counts:
        parts = [f"{k}={v}" for k, v in sorted(handoff.counts.items())]
        lines.append(f"### Counts ({', '.join(parts)})")
        lines.append("")

    parcels = handoff.parcel_metadata.get("parcels") if handoff.parcel_metadata else None
    if isinstance(parcels, list) and parcels:
        lines.append("### Parcel metadata (copied from transcript-edit)")
        for row in parcels[:12]:
            if not isinstance(row, dict):
                continue
            pid = row.get("parcel_id", "?")
            fwd = row.get("forwardable")
            scope = row.get("forwardable_scope")
            lines.append(f"- `{pid}` forwardable={fwd} scope={scope!r}")
        lines.append("")

    if handoff.issues:
        lines.append("### Issues (upstream)")
        for issue in handoff.issues[:8]:
            if isinstance(issue, dict):
                iid = issue.get("issue_id", "?")
                summary = issue.get("summary", "")
                lines.append(f"- `{iid}`: {summary}")
        lines.append("")

    if handoff.hitl_decisions:
        lines.append("### HITL decisions (upstream)")
        for row in handoff.hitl_decisions[:8]:
            if isinstance(row, dict):
                choice = row.get("choice", "")
                lines.append(f"- {choice}")
        lines.append("")

    if handoff.evidence_refs:
        lines.append("### Evidence refs")
        for ref in handoff.evidence_refs[:12]:
            lines.append(f"- `{ref}`")
        lines.append("")

    for label, key in (
        ("Normalized / mapping lane excerpt", "normalized_or_mapping_transcript"),
        ("Source verbatim lane excerpt", "source_transcript_verbatim"),
    ):
        excerpt = handoff.excerpts.get(key) if handoff.excerpts else None
        if excerpt:
            lines.append(f"### {label}")
            lines.append(excerpt)
            lines.append("")

    lines.append(
        "**Lane contract:** normalized/mapping is the primary machine-parameter lane; "
        "verbatim remains audit/source contradiction context. "
        "Preserve parcel forwardability metadata; partial/blocked scopes stay explicit."
    )
    return "\n".join(lines)
