"""Transcript-edit domain pack."""

from .domain_pack import TranscriptEditDomainPack, build_transcript_edit_domain_pack
from .execution.tool_specs import SemanticToolSpec, build_transcript_edit_tool_specs
from .manifest import TranscriptEditManifest, build_transcript_edit_manifest
from .payloads import (
    MissingResource,
    SourceImageRefDescriptor,
    T0DraftDescriptor,
    TranscriptEditDraftInventory,
    TranscriptEditScope,
    TranscriptEditStartupInventory,
)
from .prompting import (
    PromptBlock,
    build_transcript_edit_branch_blocks,
    build_transcript_edit_procedural_guidance_blocks,
)
from .semantics.closure import TranscriptEditClosureSemantics, transcript_edit_closure_semantics
from .semantics.handoff import TranscriptEditHandoffSemantics, transcript_edit_handoff_semantics
from .state import (
    CandidateRepair,
    DownstreamReadinessPosture,
    EvidencePosture,
    FinalSelectionPosture,
    TranscriptAmbiguity,
    TranscriptDefect,
    TranscriptEditProjectedView,
    TranscriptEditSemanticState,
    VerificationPosture,
    project_transcript_edit_view,
)

__all__ = [
    "CandidateRepair",
    "DownstreamReadinessPosture",
    "EvidencePosture",
    "FinalSelectionPosture",
    "MissingResource",
    "PromptBlock",
    "SemanticToolSpec",
    "SourceImageRefDescriptor",
    "T0DraftDescriptor",
    "TranscriptAmbiguity",
    "TranscriptDefect",
    "TranscriptEditDraftInventory",
    "TranscriptEditScope",
    "TranscriptEditStartupInventory",
    "TranscriptEditClosureSemantics",
    "TranscriptEditDomainPack",
    "TranscriptEditHandoffSemantics",
    "TranscriptEditManifest",
    "TranscriptEditProjectedView",
    "TranscriptEditSemanticState",
    "VerificationPosture",
    "build_transcript_edit_branch_blocks",
    "build_transcript_edit_domain_pack",
    "build_transcript_edit_manifest",
    "build_transcript_edit_procedural_guidance_blocks",
    "build_transcript_edit_tool_specs",
    "project_transcript_edit_view",
    "transcript_edit_closure_semantics",
    "transcript_edit_handoff_semantics",
]
