from __future__ import annotations

from agents.common.domain_pack_contracts import DomainManifest, DomainPackBundle, build_domain_pack_bundle

from .capabilities import build_transcript_edit_capability_requirements
from .handoff import build_transcript_edit_handoff_postures


def build_transcript_edit_domain_manifest() -> DomainManifest:
    return DomainManifest(
        domain_id="transcript_edit",
        family_id="mapping",
        display_name="Transcript Edit",
        capability_requirements=build_transcript_edit_capability_requirements(),
        supported_handoffs=build_transcript_edit_handoff_postures(),
        compatibility_status="compatible",
    )


def build_transcript_edit_domain_pack_bundle(domain_pack: object) -> DomainPackBundle:
    bundle = build_domain_pack_bundle(
        manifest=build_transcript_edit_domain_manifest(),
        domain_pack=domain_pack,
        prompt_branch_source_ref="agents.transcript_edit.prompt_sources",
    )
    binder = getattr(domain_pack, "bind_domain_bundle", None)
    if callable(binder):
        binder(bundle)
    return bundle
