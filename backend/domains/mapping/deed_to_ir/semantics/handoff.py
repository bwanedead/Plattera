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
            "Deed-to-IR consumes transcript-edit output and resolution-state context to produce "
            "source-traceable feature-graph IR and an honest scoped mapping handoff."
        ),
        ready_when=(
            "Startup handoff exposes transcript lanes, parcel metadata, issues, evidence refs, and resolution-state context.",
            "Forwardable and blocked scopes remain explicit rather than being collapsed into whole-deed readiness.",
            "IR entities can retain exact links to the upstream resolution units that justify them.",
        ),
        artifact_expectations=(
            "Transcript-edit source revision identity without model-facing filesystem paths.",
            "Parcel scope metadata, issues, HITL decisions, and resolution-state identity preserved mechanically.",
            "Durable feature-graph artifacts preserve agent-authored source-entity provenance links.",
        ),
        should_not_hand_off_yet=(
            "Treating normalized transcript as a substitute for IR artifacts.",
            "Treating valid IR or a rendered result as proof of deed fidelity by itself.",
            "Rewriting transcript-edit blockers or forwardability in deterministic code.",
        ),
    )
