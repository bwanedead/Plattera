"""Universal prompt identity composer.

This module owns prompt assembly, not authored source text. Shared trunk source
blocks live in ``domains.common.prompt_sources``; domain branch doctrine lives in
domain-local prompt source modules where practical. This file prepends the
identity header and composes those blocks for each LLM surface.

run_link_id is the canonical mission-level linkage string. It must be set once
per mission run (at request_id_prefix / session scope) and passed unchanged to
every compose call for that run, regardless of surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .prompt_observability import PromptEventMetadata, PromptSourceBlockRef, build_prompt_event_metadata
from .prompt_sources import PromptSourceBlock, build_shared_harness_trunk_blocks, compose_prompt_source_text
from domains.mapping.deed_to_ir.prompt_sources import build_deed_to_ir_branch_blocks
from domains.mapping.transcript_edit.prompt_sources import build_transcript_edit_branch_blocks


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Domain(str, Enum):
    TRANSCRIPT_EDIT = "transcript_edit"
    DEED_TO_IR = "deed_to_ir"
    GENERIC = "generic"


class Surface(str, Enum):
    # Transcript-edit surfaces
    TX_FOCUS_RESOLVER = "tx_focus_resolver"
    TX_PLANNER = "tx_planner"
    TX_ORIENT_BASELINE = "tx_orient_baseline"
    TX_IMAGE_LOCATOR = "tx_image_locator"
    TX_IMAGE_VERIFIER = "tx_image_verifier"
    # Deed-to-IR surfaces
    DEED_CONTROLLER = "deed_controller"
    DEED_CONTROLLER_REPAIR = "deed_controller_repair"
    # Generic
    GENERIC = "generic"


class InheritanceMode(str, Enum):
    FULL = "full"
    LIGHT = "light"


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IdentityMetadata:
    constitution_version: str
    domain: str
    surface: str
    inheritance_mode: str
    run_link_id: str
    model: str
    mission_objective: str


@dataclass(frozen=True)
class IdentityResult:
    """Returned by compose_identity_header().

    header_text: prepend this to the leaf system/developer message.
    metadata: structured record for trace emission.
    """

    header_text: str
    metadata: IdentityMetadata
    source_blocks: tuple[PromptSourceBlockRef, ...] = ()
    prompt_event_metadata: PromptEventMetadata | None = None


_CONSTITUTION_VERSION = "v2"

# Public alias — importable by callers who need to stamp the current version without
# hard-coding the string (e.g. domain packs that pass constitution_version= kwargs).
CONSTITUTION_VERSION = _CONSTITUTION_VERSION


def _render_identity_header(*, version: str, run_link_id: str, mission_objective: str, domain: str, surface: str) -> str:
    return (
        f"[IDENTITY constitution={version}]\n"
        f"run_link_id: {run_link_id}\n"
        f"mission_objective: {mission_objective}\n"
        f"domain: {domain}\n"
        f"surface: {surface}\n"
        f"constitution_version: {version}\n\n"
    )


def _block_refs(blocks: tuple[PromptSourceBlock, ...]) -> tuple[PromptSourceBlockRef, ...]:
    return tuple(block.as_ref() for block in blocks)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compose_identity_header(
    *,
    run_link_id: str,
    mission_objective: str = "",
    domain: Domain = Domain.GENERIC,
    surface: Surface = Surface.GENERIC,
    inheritance_mode: InheritanceMode = InheritanceMode.FULL,
    model: str = "",
    constitution_version: str = _CONSTITUTION_VERSION,
) -> IdentityResult:
    """Compose trunk + branch identity header for a single LLM call surface.

    Args:
        run_link_id: canonical mission-level linkage string (= request_id_prefix).
            Must be the same value for all surfaces within one mission run.
        mission_objective: human-readable mission purpose string.
        domain: which product domain this surface belongs to.
        surface: the specific LLM call surface (recorded in the canonical
            identity header block and in trace metadata).
        inheritance_mode: FULL assembles both trunk and branch texts; LIGHT
            assembles abbreviated versions for micro-surfaces.
        model: model identifier for the call (recorded in metadata/trace).
        constitution_version: trunk/branch schema version (default "v2").

    Returns:
        IdentityResult with header_text (prepend to leaf) and metadata (for
        trace emission).
    """
    version = str(constitution_version or _CONSTITUTION_VERSION).strip() or _CONSTITUTION_VERSION
    run_id = str(run_link_id or "").strip() or "unknown"
    obj = str(mission_objective or "").strip() or "not specified"
    mdl = str(model or "").strip() or "unknown"

    trunk_blocks = build_shared_harness_trunk_blocks(
        constitution_version=version,
        inheritance_mode=inheritance_mode.value,
    )
    if domain == Domain.TRANSCRIPT_EDIT:
        branch_blocks = build_transcript_edit_branch_blocks(inheritance_mode=inheritance_mode.value)
    elif domain == Domain.DEED_TO_IR:
        branch_blocks = build_deed_to_ir_branch_blocks(
            inheritance_mode=inheritance_mode.value,
            version=version,
        )
    else:
        branch_blocks = ()

    source_blocks = trunk_blocks + branch_blocks
    header = _render_identity_header(
        version=version,
        run_link_id=run_id,
        mission_objective=obj,
        domain=domain.value,
        surface=surface.value,
    )
    header += compose_prompt_source_text(source_blocks)

    metadata = IdentityMetadata(
        constitution_version=version,
        domain=domain.value,
        surface=surface.value,
        inheritance_mode=inheritance_mode.value,
        run_link_id=run_id,
        model=mdl,
        mission_objective=obj,
    )
    block_refs = _block_refs(source_blocks)
    prompt_event_metadata = build_prompt_event_metadata(
        run_link_id=run_id,
        run_id=run_id,
        iteration_index=None,
        surface=surface.value,
        domain=domain.value,
        model=mdl,
        constitution_version=version,
        composition_mode=inheritance_mode.value,
        source_blocks=block_refs,
    )
    return IdentityResult(
        header_text=header,
        metadata=metadata,
        source_blocks=block_refs,
        prompt_event_metadata=prompt_event_metadata,
    )

