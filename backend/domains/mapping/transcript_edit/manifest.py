"""Transcript-edit domain identity and declaration (no runtime logic)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TranscriptEditManifest:
    domain_id: str = "transcript_edit"
    family_id: str = "mapping"
    display_name: str = "Transcript Edit"
    prompt_branch_source_ref: str = "domains.mapping.transcript_edit.prompting.branch"
    prompt_support_source_refs: tuple[str, ...] = (
        "domains.mapping.transcript_edit.prompting.surfaces.procedural_guidance",
    )
    tool_specs_module_ref: str = "domains.mapping.transcript_edit.execution.tool_specs"
    state_contracts_module_ref: str = "domains.mapping.transcript_edit.state.contracts"
    projection_module_ref: str = "domains.mapping.transcript_edit.state.projection"
    closure_module_ref: str = "domains.mapping.transcript_edit.semantics.closure"
    handoff_module_ref: str = "domains.mapping.transcript_edit.semantics.handoff"
    semantic_surfaces: tuple[str, ...] = (
        "prompting.branch",
        "prompting.surfaces.procedural_guidance",
        "prompting.surfaces.startup_context",
        "state.contracts",
        "state.projection",
        "execution.tool_specs",
        "semantics.closure",
        "semantics.handoff",
    )
    declared_semantic_tool_ids: tuple[str, ...] = ()


def build_transcript_edit_manifest() -> TranscriptEditManifest:
    """Tool ids are derived from ``execution.tool_specs`` so manifest and specs cannot drift."""

    from .execution.tool_specs import build_transcript_edit_tool_specs

    specs = build_transcript_edit_tool_specs()
    return TranscriptEditManifest(
        declared_semantic_tool_ids=tuple(s.tool_id for s in specs),
    )
