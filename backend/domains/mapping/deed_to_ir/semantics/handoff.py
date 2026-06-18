"""Readiness boundaries for deed-to-IR — semantic contract only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeedToIrHandoffSemantics:
    summary: str
    ready_when: tuple[str, ...]
    artifact_expectations: tuple[str, ...]
    should_not_hand_off_yet: tuple[str, ...]


def deed_to_ir_handoff_semantics() -> DeedToIrHandoffSemantics:
    return DeedToIrHandoffSemantics(
        summary=(
            "Deed-to-IR consumes transcript-edit output lanes and parcel forwardability metadata. "
            "The job is representable feature-graph IR, not forced geometry compilation."
        ),
        ready_when=(
            "Startup handoff exposes normalized and verbatim transcript lanes plus parcel metadata.",
            "Forwardable vs blocked scopes are inventoried from inherited metadata.",
            "IR authoring tools (future passes) can attach to scoped work without re-litigating transcript truth.",
        ),
        artifact_expectations=(
            "Transcript-edit output ref or path with source_revision_ref when available.",
            "parcel_metadata.parcels forwardability copied forward unchanged.",
            "issues and hitl_decisions available for orientation, not re-adjudication by harness.",
        ),
        should_not_hand_off_yet=(
            "Treating normalized transcript as a substitute for IR artifacts.",
            "Assuming compile/judge success before those tools exist.",
            "Rewriting transcript-edit blockers or forwardability in deterministic code.",
        ),
    )
