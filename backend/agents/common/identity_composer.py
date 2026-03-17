"""Universal prompt identity composer.

Assembles trunk (universal harness laws) + branch (domain overlay) + metadata
for every LLM call surface in the Plattera harness.  The caller prepends the
resulting header_text to its own leaf (surface-specific system/developer
message).

run_link_id is the canonical mission-level linkage string.  It must be set
once per mission run (at request_id_prefix / session scope) and passed
unchanged to every compose call for that run, regardless of surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


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


# ---------------------------------------------------------------------------
# Versioned trunk text
# ---------------------------------------------------------------------------

_CONSTITUTION_VERSION = "v1"

_TRUNK_FULL_TMPL = (
    "[IDENTITY constitution={version}]\n"
    "run_link_id: {run_link_id}\n"
    "mission_objective: {mission_objective}\n"
    "domain: {domain}\n"
    "surface: {surface}\n"
    "constitution_version: {version}\n"
    "[TRUNK:root_constitution_{version}]\n"
    "Universal harness laws:\n"
    "- Return only valid JSON. Never output prose or markdown.\n"
    "- Be faithful to source material. Do not invent, substitute, or hallucinate.\n"
    "- Prefer artifact refs over large inline payloads.\n"
    "[WORKFLOW:ontology_{version}]\n"
    "This call is one bounded step inside an ongoing run; it has no persistent chat memory.\n"
    "Continuity is carried by run identity, prior artifacts, the focus packet, and bounded"
    " recency summaries injected into this prompt — not by conversational context.\n"
    "Every local action must advance the mission objective under the shared constitution;"
    " do not drift or reframe the goal.\n"
    "\n"
)

_TRUNK_LIGHT_TMPL = (
    "[IDENTITY constitution={version}]\n"
    "run_link_id: {run_link_id}\n"
    "mission_objective: {mission_objective}\n"
    "domain: {domain}\n"
    "surface: {surface}\n"
    "constitution_version: {version}\n"
    "[TRUNK:root_constitution_{version} mode=light]\n"
    "Return valid JSON only. Be faithful to source material.\n"
    "[WORKFLOW:ontology_{version} mode=light]\n"
    "One bounded step in an ongoing run; continuity via run identity, artifacts, and packet"
    " (not chat memory). Advance the mission objective only.\n"
    "\n"
)

# ---------------------------------------------------------------------------
# Versioned branch text — transcript-edit domain
# ---------------------------------------------------------------------------

_BRANCH_TX_FULL_TMPL = (
    "[BRANCH:transcript_edit_{version}]\n"
    "Domain: transcript edit loop.\n"
    "Mapping-blocking unresolved items are the highest priority focus.\n"
    "Decisions must be grounded in evidence from the source transcript or deed image.\n"
    "When HITL feedback is present for the focused item, it is authoritative operator signal.\n"
    "Never finalize a blocked item without evidence or explicit human guidance.\n"
    "\n"
)

_BRANCH_TX_LIGHT_TMPL = (
    "[BRANCH:transcript_edit_{version} mode=light]\n"
    "Domain: transcript edit."
    " Mapping-blocking items have priority. Faithfulness to source is required.\n"
    "\n"
)

# ---------------------------------------------------------------------------
# Versioned branch text — deed-to-IR domain
# ---------------------------------------------------------------------------

_BRANCH_DEED_FULL_TMPL = (
    "[BRANCH:deed_to_ir_{version}]\n"
    "Domain: deed-to-IR FeatureGraph mapping loop.\n"
    "Faithful representation of deed semantics takes priority over forcing a convenient graph.\n"
    "Structural gates (compile/judge) are necessary but not sufficient for done.\n"
    "Do not finalize placeholder or sketch geometry as a mapped result.\n"
    "\n"
)

_BRANCH_DEED_LIGHT_TMPL = (
    "[BRANCH:deed_to_ir_{version} mode=light]\n"
    "Domain: deed-to-IR mapping. Faithfulness to deed semantics is required.\n"
    "\n"
)

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
        constitution_version: trunk/branch schema version (default "v1").

    Returns:
        IdentityResult with header_text (prepend to leaf) and metadata (for
        trace emission).
    """
    version = str(constitution_version or _CONSTITUTION_VERSION).strip() or _CONSTITUTION_VERSION
    run_id = str(run_link_id or "").strip() or "unknown"
    obj = str(mission_objective or "").strip() or "not specified"
    mdl = str(model or "").strip() or "unknown"

    ctx = {
        "version": version,
        "run_link_id": run_id,
        "model": mdl,
        "mission_objective": obj,
        "domain": domain.value,
        "surface": surface.value,
    }

    is_light = inheritance_mode == InheritanceMode.LIGHT

    trunk = (_TRUNK_LIGHT_TMPL if is_light else _TRUNK_FULL_TMPL).format(**ctx)

    if domain == Domain.TRANSCRIPT_EDIT:
        branch = (_BRANCH_TX_LIGHT_TMPL if is_light else _BRANCH_TX_FULL_TMPL).format(**ctx)
    elif domain == Domain.DEED_TO_IR:
        branch = (_BRANCH_DEED_LIGHT_TMPL if is_light else _BRANCH_DEED_FULL_TMPL).format(**ctx)
    else:
        branch = ""

    header = trunk + branch

    metadata = IdentityMetadata(
        constitution_version=version,
        domain=domain.value,
        surface=surface.value,
        inheritance_mode=inheritance_mode.value,
        run_link_id=run_id,
        model=mdl,
        mission_objective=obj,
    )
    return IdentityResult(header_text=header, metadata=metadata)
