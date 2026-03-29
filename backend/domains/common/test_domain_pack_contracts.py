from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.common.domain_pack_contracts import (
    CapabilityRequirement,
    DomainHandoffPosture,
    DomainManifest,
    DomainPackBundle,
    build_domain_pack_bundle,
)


def test_domain_manifest_groups_identity_and_capability_requirements() -> None:
    requirements = (
        CapabilityRequirement(
            capability_id="transcript_audit",
            required=True,
            category="evidence",
            notes="Needs transcript inspection.",
        ),
        CapabilityRequirement(
            capability_id="edit_application",
            required=False,
            category="execution",
        ),
    )
    handoffs = (
        DomainHandoffPosture(
            posture="ready_for_downstream_domain",
            target_domain_id="deed_to_ir",
            reason_code="closure_clear",
            summary="Ready to hand off after transcript verification.",
        ),
    )

    manifest = DomainManifest(
        domain_id="transcript_edit",
        family_id="mapping",
        display_name="Transcript Edit",
        capability_requirements=requirements,
        supported_handoffs=handoffs,
        compatibility_status="compatible",
    )

    assert manifest.domain_id == "transcript_edit"
    assert manifest.family_id == "mapping"
    assert manifest.display_name == "Transcript Edit"
    assert manifest.capability_requirements == requirements
    assert manifest.supported_handoffs == handoffs
    assert manifest.compatibility_status == "compatible"


def test_domain_handoff_posture_construction_is_explicit() -> None:
    posture = DomainHandoffPosture(
        posture="blocked_pending_dependency",
        target_family_id="mapping",
        reason_code="missing_image_evidence",
        summary="Cannot hand off until image evidence is available.",
        domain_payload={"missing_capability": "image_evidence"},
    )

    assert posture.posture == "blocked_pending_dependency"
    assert posture.target_domain_id is None
    assert posture.target_family_id == "mapping"
    assert posture.reason_code == "missing_image_evidence"
    assert posture.summary == "Cannot hand off until image evidence is available."
    assert posture.domain_payload == {"missing_capability": "image_evidence"}


def test_domain_pack_bundle_groups_manifest_adapter_and_prompt_source_reference() -> None:
    manifest = DomainManifest(
        domain_id="transcript_edit",
        family_id="mapping",
        display_name="Transcript Edit",
        compatibility_status="compatible",
    )
    adapter = object()
    bundle = DomainPackBundle(
        manifest=manifest,
        domain_pack=adapter,
        prompt_branch_source_ref="backend/domains/mapping/transcript_edit/prompt_sources.py",
    )

    assert bundle.manifest is manifest
    assert bundle.domain_pack is adapter
    assert bundle.prompt_branch_source_ref == "backend/domains/mapping/transcript_edit/prompt_sources.py"


def test_build_domain_pack_bundle_wraps_bundle_mechanics_without_extra_policy() -> None:
    manifest = DomainManifest(
        domain_id="deed_to_ir",
        family_id="mapping",
        display_name="Deed to IR",
    )
    adapter = object()

    bundle = build_domain_pack_bundle(
        manifest=manifest,
        domain_pack=adapter,
        prompt_branch_source_ref="domains.mapping.deed_to_ir.prompt_sources",
    )

    assert isinstance(bundle, DomainPackBundle)
    assert bundle.manifest is manifest
    assert bundle.domain_pack is adapter
    assert bundle.prompt_branch_source_ref == "domains.mapping.deed_to_ir.prompt_sources"

