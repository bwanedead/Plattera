from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent_kernel.actions import ActionExecutorDeps, ProviderStepResultProjector, RegisteredProviderAction
from agent_kernel.harness_action_ids import ActionType

from .capabilities import build_transcript_edit_capability_requirements
from .execution_action_ids import (
    TX_APPLY_EDIT_PLAN,
    TX_AUDIT_TRANSCRIPT,
    TX_OPEN_TRANSCRIPT_SPANS,
    TX_ORIENT_AND_BASELINE,
    TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
    TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
)
from .kernel_action_registration import build_transcript_edit_provider_actions
from .provider_step_projections import build_transcript_edit_provider_step_projectors


@dataclass(frozen=True)
class TranscriptEditCapabilityBinding:
    """Concrete composition result for one declared transcript-edit capability."""

    capability_id: str
    required: bool
    wiring_kind: str | None
    wiring_name: str | None
    satisfied: bool
    notes: str | None = None


@dataclass(frozen=True)
class TranscriptEditCapabilityWiring:
    """Resolved transcript-edit capability wiring for one composed executor."""

    capability_bindings: tuple[TranscriptEditCapabilityBinding, ...]
    capability_to_action_ids: dict[str, tuple[str, ...]] = field(default_factory=dict)
    provider_actions: dict[str, RegisteredProviderAction] = field(default_factory=dict)
    provider_step_projectors: dict[str, ProviderStepResultProjector] = field(default_factory=dict)
    action_executor_deps: ActionExecutorDeps | None = None
    missing_required_capabilities: tuple[str, ...] = ()


class TranscriptEditMissingCapabilityError(ValueError):
    """Raised when required transcript-edit capabilities are not wired."""


def build_transcript_edit_capability_wiring(
    *,
    transcript_auditor: Any | None,
    transcript_orient_baseliner: Any | None,
    transcript_span_opener: Any | None,
    transcript_image_verifier: Any | None,
    transcript_plan_applier: Any | None,
    transcript_span_seeds_saver: Any | None,
    transcript_promoter: Any | None,
    evidence_retriever: Any | None,
) -> TranscriptEditCapabilityWiring:
    """Resolve declared transcript-edit capabilities into explicit runtime wiring."""

    requirements = build_transcript_edit_capability_requirements()
    requirement_by_id = {item.capability_id: item for item in requirements}

    def _required(capability_id: str) -> bool:
        requirement = requirement_by_id.get(capability_id)
        if requirement is None:
            raise KeyError(f"transcript_edit_missing_capability_requirement:{capability_id}")
        return bool(requirement.required)

    provider_actions = build_transcript_edit_provider_actions(
        transcript_auditor=transcript_auditor,
        transcript_orient_baseliner=transcript_orient_baseliner,
        transcript_span_opener=transcript_span_opener,
        transcript_image_verifier=transcript_image_verifier,
        transcript_plan_applier=transcript_plan_applier,
        transcript_span_seeds_saver=transcript_span_seeds_saver,
        transcript_promoter=transcript_promoter,
    )
    provider_step_projectors = build_transcript_edit_provider_step_projectors()

    capability_to_action_ids: dict[str, tuple[str, ...]] = {
        "transcript_orientation": (TX_ORIENT_AND_BASELINE,),
        "transcript_audit": (TX_AUDIT_TRANSCRIPT,),
        "span_opening": (TX_OPEN_TRANSCRIPT_SPANS,),
        "image_evidence": (TX_VERIFY_TRANSCRIPT_WITH_IMAGE,),
        "edit_application": (TX_APPLY_EDIT_PLAN,),
        "feedback_prompting": (),
        "transcript_promotion": (TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,),
        "retrieve_evidence": (ActionType.RETRIEVE_EVIDENCE.value,),
    }

    capability_bindings = (
        TranscriptEditCapabilityBinding(
            capability_id="transcript_orientation",
            required=_required("transcript_orientation"),
            wiring_kind="provider_action",
            wiring_name=TX_ORIENT_AND_BASELINE,
            satisfied=transcript_orient_baseliner is not None,
            notes="Resolved by the transcript orient/baseline provider action.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="transcript_audit",
            required=_required("transcript_audit"),
            wiring_kind="provider_action",
            wiring_name=TX_AUDIT_TRANSCRIPT,
            satisfied=transcript_auditor is not None,
            notes="Resolved by the transcript audit provider action.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="span_opening",
            required=_required("span_opening"),
            wiring_kind="provider_action",
            wiring_name=TX_OPEN_TRANSCRIPT_SPANS,
            satisfied=transcript_span_opener is not None,
            notes="Resolved by the bounded span opener provider action.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="image_evidence",
            required=_required("image_evidence"),
            wiring_kind="provider_action",
            wiring_name=TX_VERIFY_TRANSCRIPT_WITH_IMAGE,
            satisfied=transcript_image_verifier is not None,
            notes="Resolved by the image-evidence provider action.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="edit_application",
            required=_required("edit_application"),
            wiring_kind="provider_action",
            wiring_name=TX_APPLY_EDIT_PLAN,
            satisfied=transcript_plan_applier is not None,
            notes="Resolved by the edit-plan apply provider action.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="feedback_prompting",
            required=_required("feedback_prompting"),
            wiring_kind="runtime_seam",
            wiring_name="feedback_lifecycle",
            satisfied=True,
            notes="Kept at the transcript-edit feedback lifecycle seam for now.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="transcript_promotion",
            required=_required("transcript_promotion"),
            wiring_kind="provider_action",
            wiring_name=TX_PROMOTE_TRANSCRIPT_FOR_MAPPING,
            satisfied=transcript_promoter is not None,
            notes="Resolved by the downstream transcript promotion provider action.",
        ),
        TranscriptEditCapabilityBinding(
            capability_id="retrieve_evidence",
            required=_required("retrieve_evidence"),
            wiring_kind="executor_interface",
            wiring_name="evidence_retriever",
            satisfied=evidence_retriever is not None,
            notes="Resolved by the shared ActionExecutor evidence retriever interface.",
        ),
    )

    missing_required_capabilities = tuple(
        binding.capability_id for binding in capability_bindings if binding.required and not binding.satisfied
    )
    if missing_required_capabilities:
        raise TranscriptEditMissingCapabilityError(
            "transcript_edit_missing_required_capabilities:" + ",".join(missing_required_capabilities)
        )

    return TranscriptEditCapabilityWiring(
        capability_bindings=capability_bindings,
        capability_to_action_ids=capability_to_action_ids,
        provider_actions=provider_actions,
        provider_step_projectors=provider_step_projectors,
        action_executor_deps=ActionExecutorDeps(
            evidence_retriever=evidence_retriever,
            provider_actions=provider_actions,
            provider_step_projectors=provider_step_projectors,
        ),
        missing_required_capabilities=missing_required_capabilities,
    )


def build_transcript_edit_action_executor_deps(
    *,
    transcript_auditor: Any | None,
    transcript_orient_baseliner: Any | None,
    transcript_span_opener: Any | None,
    transcript_image_verifier: Any | None,
    transcript_plan_applier: Any | None,
    transcript_span_seeds_saver: Any | None,
    transcript_promoter: Any | None,
    evidence_retriever: Any | None,
) -> ActionExecutorDeps:
    """Build the shared executor dependency bundle for transcript-edit composition."""

    return build_transcript_edit_capability_wiring(
        transcript_auditor=transcript_auditor,
        transcript_orient_baseliner=transcript_orient_baseliner,
        transcript_span_opener=transcript_span_opener,
        transcript_image_verifier=transcript_image_verifier,
        transcript_plan_applier=transcript_plan_applier,
        transcript_span_seeds_saver=transcript_span_seeds_saver,
        transcript_promoter=transcript_promoter,
        evidence_retriever=evidence_retriever,
    ).action_executor_deps
