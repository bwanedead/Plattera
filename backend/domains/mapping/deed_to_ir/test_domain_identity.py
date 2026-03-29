from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from backend.domains.mapping.deed_to_ir import (
    build_deed_to_ir_capability_requirements,
    build_deed_to_ir_domain_manifest,
    build_deed_to_ir_domain_pack_bundle,
    build_deed_to_ir_supported_handoffs,
)
from backend.domains.mapping.deed_to_ir.handoff import build_deed_to_ir_handoff_posture


class _StubDomainPack:
    def __init__(self) -> None:
        self.bound_bundle = None

    def bind_domain_bundle(self, bundle) -> None:
        self.bound_bundle = bundle


def test_deed_identity_surface_declares_expected_capabilities_and_handoff() -> None:
    manifest = build_deed_to_ir_domain_manifest()
    assert manifest.domain_id == "deed_to_ir"
    assert manifest.family_id == "mapping"
    assert manifest.display_name == "Deed to IR"

    capability_ids = [cap.capability_id for cap in manifest.capability_requirements]
    assert capability_ids == [
        "retrieve_evidence",
        "edit_application",
        "feedback_prompting",
    ]

    handoffs = build_deed_to_ir_supported_handoffs()
    assert len(handoffs) == 1
    assert handoffs[0].posture == "ready_for_downstream_domain"
    assert handoffs[0].target_domain_id == "transcript_edit"


def test_deed_capability_requirements_are_explicit_and_bounded() -> None:
    requirements = build_deed_to_ir_capability_requirements()
    assert [req.capability_id for req in requirements] == [
        "retrieve_evidence",
        "edit_application",
        "feedback_prompting",
    ]
    assert requirements[0].required is True
    assert requirements[2].required is False


def test_deed_bundle_binds_manifest_and_prompt_branch_source() -> None:
    domain_pack = _StubDomainPack()
    bundle = build_deed_to_ir_domain_pack_bundle(domain_pack)

    assert domain_pack.bound_bundle is bundle
    assert bundle.manifest.domain_id == "deed_to_ir"
    assert bundle.manifest.family_id == "mapping"
    assert bundle.prompt_branch_source_ref == "domains.mapping.deed_to_ir.prompt_sources"


def test_deed_handoff_posture_derivation_is_explicit() -> None:
    ready = build_deed_to_ir_handoff_posture(
        failure_classification={"stop_reason": "completed", "reason_code": "done"},
        claimability={"claimable_ready": True, "missing_claimability": []},
    )
    blocked = build_deed_to_ir_handoff_posture(
        failure_classification={"stop_reason": "needs_upload", "reason_code": "missing_dependency"},
        claimability={"claimable_ready": False, "missing_claimability": ["has_georef"]},
    )
    waiting = build_deed_to_ir_handoff_posture(
        failure_classification={"stop_reason": "needs_user_choice", "reason_code": "waiting_for_choice"},
        claimability={"claimable_ready": False, "missing_claimability": []},
    )
    none = build_deed_to_ir_handoff_posture(
        failure_classification={"stop_reason": "completed", "reason_code": "done"},
        claimability={"claimable_ready": False, "missing_claimability": []},
    )

    assert ready.posture == "ready_for_downstream_domain"
    assert blocked.posture == "blocked_pending_dependency"
    assert waiting.posture == "waiting_on_human"
    assert none.posture == "no_handoff"

