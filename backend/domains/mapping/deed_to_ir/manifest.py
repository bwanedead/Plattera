"""Deed-to-IR domain identity and declaration (no runtime logic)."""

from __future__ import annotations

from dataclasses import dataclass, field

from domains.closure_policy import DomainClosurePolicy
from domains.work_graph_policy import DomainWorkGraphPolicy, default_work_graph_policy
from .semantics.closure import build_deed_to_ir_closure_policy


@dataclass(frozen=True)
class DeedToIrManifest:
    domain_id: str = "deed_to_ir"
    family_id: str = "mapping"
    display_name: str = "Deed To IR"
    family_prompt_branch_source_ref: str = "domains.mapping.prompting.family_branch"
    prompt_branch_source_ref: str = "domains.mapping.deed_to_ir.prompting.branch"
    prompt_support_source_refs: tuple[str, ...] = (
        "domains.mapping.deed_to_ir.prompting.surfaces.procedural_guidance",
    )
    startup_context_source_ref: str = "domains.mapping.deed_to_ir.prompting.surfaces.startup_context"
    tool_specs_module_ref: str = "domains.mapping.deed_to_ir.execution.tool_specs"
    state_contracts_module_ref: str = "domains.mapping.deed_to_ir.state.contracts"
    projection_module_ref: str = ""
    prompt_runtime_projection_module_ref: str = (
        "domains.mapping.deed_to_ir.state.prompt_runtime_projection"
    )
    closure_module_ref: str = "domains.mapping.deed_to_ir.semantics.closure"
    handoff_module_ref: str = "domains.mapping.deed_to_ir.semantics.handoff"
    closure_policy: DomainClosurePolicy = field(default_factory=build_deed_to_ir_closure_policy)
    work_graph_policy: DomainWorkGraphPolicy = field(default_factory=default_work_graph_policy)
    declared_semantic_tool_ids: tuple[str, ...] = ()


def build_deed_to_ir_manifest() -> DeedToIrManifest:
    from .execution.tool_specs import build_deed_to_ir_tool_specs

    specs = build_deed_to_ir_tool_specs()
    return DeedToIrManifest(
        declared_semantic_tool_ids=tuple(s.tool_id for s in specs),
    )
