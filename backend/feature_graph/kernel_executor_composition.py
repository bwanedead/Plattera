"""Product-default kernel executor wiring (Phase 34).

This is **application composition**, not harness identity: deed/FG and transcript-edit tools are
registered here so ``KernelSessionManager`` can stay a generic execution host.
"""

from __future__ import annotations

from typing import Any

from agent_kernel.actions import ActionExecutor, ActionExecutorDeps
from agent_kernel.session import KernelSessionManager, SessionPersistence, build_kernel_session_manager
from agent_kernel.tooling import (
    CorpusArtifactOpener,
    CorpusDeedHydrator,
    DeedSpanIndexUpserterTool,
    DraftIRFilesystemProposer,
    TranscriptAuditTool,
    TranscriptEditPlanApplyTool,
    TranscriptImageVerificationTool,
    TranscriptMappingPromoterTool,
    TranscriptSpanOpenerTool,
    TranscriptSpanSeedsSaverTool,
    TextSpanOpenerTool,
)
from agent_kernel.tooling import (
    FeatureGraphBundlerTool,
    FeatureGraphCompilerTool,
    FeatureGraphGeoreferenceTool,
    FeatureGraphJudgeTool,
    FeatureGraphRenderTool,
    FeatureGraphValidateTool,
    RetrievalEvidenceTool,
)

from .kernel_step_projections import build_feature_graph_provider_step_projectors
from .kernel_claimability import FeatureGraphClaimabilityPolicy
from .kernel_terminal_hooks import mark_final_feature_graph_pointers


def _default_transcript_orient_baseliner() -> Any:
    from domains.mapping.transcript_edit.orient_tool import TranscriptOrientBaselineTool

    return TranscriptOrientBaselineTool()


def _default_transcript_edit_provider_actions() -> dict[str, Any]:
    from domains.mapping.transcript_edit.kernel_action_registration import build_transcript_edit_provider_actions

    return build_transcript_edit_provider_actions(
        transcript_auditor=TranscriptAuditTool(),
        transcript_orient_baseliner=_default_transcript_orient_baseliner(),
        transcript_span_opener=TranscriptSpanOpenerTool(),
        transcript_image_verifier=TranscriptImageVerificationTool(),
        transcript_plan_applier=TranscriptEditPlanApplyTool(),
        transcript_span_seeds_saver=TranscriptSpanSeedsSaverTool(),
        transcript_promoter=TranscriptMappingPromoterTool(),
    )


def _default_combined_step_projectors() -> dict[str, Any]:
    from domains.mapping.transcript_edit.provider_step_projections import build_transcript_edit_provider_step_projectors

    fg = build_feature_graph_provider_step_projectors()
    tx = build_transcript_edit_provider_step_projectors()
    return {**fg, **tx}


def build_plattera_default_action_executor() -> ActionExecutor:
    """Default desktop product wiring: FG/deed tools + transcript-edit provider registration."""
    return ActionExecutor(
        deps=ActionExecutorDeps(
            artifact_hydrator=CorpusDeedHydrator(),
            artifact_opener=CorpusArtifactOpener(),
            text_span_opener=TextSpanOpenerTool(),
            artifact_draft_proposer=DraftIRFilesystemProposer(),
            span_index_upserter=DeedSpanIndexUpserterTool(),
            evidence_retriever=RetrievalEvidenceTool(),
            artifact_compiler=FeatureGraphCompilerTool(),
            artifact_judge=FeatureGraphJudgeTool(),
            artifact_bundler=FeatureGraphBundlerTool(),
            artifact_georeferencer=FeatureGraphGeoreferenceTool(),
            artifact_validator=FeatureGraphValidateTool(),
            artifact_renderer=FeatureGraphRenderTool(),
            provider_actions=_default_transcript_edit_provider_actions(),
            provider_step_projectors=_default_combined_step_projectors(),
            terminal_success_hooks=(mark_final_feature_graph_pointers,),
        )
    )


def build_plattera_default_kernel_session_manager(
    *,
    persistence_service: SessionPersistence | None = None,
) -> KernelSessionManager:
    """Product-owned convenience composition for app/bootstrap callers."""
    return build_kernel_session_manager(
        action_executor=build_plattera_default_action_executor(),
        claimability_policy=FeatureGraphClaimabilityPolicy(),
        persistence_service=persistence_service,
    )

