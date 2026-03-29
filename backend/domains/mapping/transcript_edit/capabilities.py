from __future__ import annotations

from domains.common.domain_pack_contracts import CapabilityRequirement


def build_transcript_edit_capability_requirements() -> tuple[CapabilityRequirement, ...]:
    return (
        CapabilityRequirement(
            capability_id="transcript_orientation",
            required=True,
            category="state",
            notes="Needs transcript-specific orientation and reconciliation.",
        ),
        CapabilityRequirement(
            capability_id="transcript_audit",
            required=True,
            category="evidence",
            notes="Needs transcript audit and reread capability.",
        ),
        CapabilityRequirement(
            capability_id="span_opening",
            required=False,
            category="evidence",
            notes="May open transcript spans during evidence gathering.",
        ),
        CapabilityRequirement(
            capability_id="image_evidence",
            required=False,
            category="evidence",
            notes="May inspect image-backed evidence when available.",
        ),
        CapabilityRequirement(
            capability_id="edit_application",
            required=True,
            category="execution",
            notes="Needs bounded edit execution for transcript updates.",
        ),
        CapabilityRequirement(
            capability_id="feedback_prompting",
            required=False,
            category="feedback",
            notes="May request human feedback when closure is blocked.",
        ),
        CapabilityRequirement(
            capability_id="transcript_promotion",
            required=False,
            category="handoff",
            notes="May hand off promoted transcript artifacts downstream.",
        ),
        CapabilityRequirement(
            capability_id="retrieve_evidence",
            required=True,
            category="evidence",
            notes="Needs bounded retrieval of supporting evidence.",
        ),
    )

