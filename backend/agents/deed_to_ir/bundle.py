"""Deed-to-IR pack bundle construction."""

from __future__ import annotations

from typing import Any

from agents.common.domain_pack_contracts import DomainPackBundle, build_domain_pack_bundle

from .manifest import build_deed_to_ir_domain_manifest


def build_deed_to_ir_domain_pack_bundle(domain_pack: Any) -> DomainPackBundle:
    """Build and bind the explicit shared bundle for deed-to-IR composition."""

    bundle = build_domain_pack_bundle(
        manifest=build_deed_to_ir_domain_manifest(),
        domain_pack=domain_pack,
        prompt_branch_source_ref="agents.deed_to_ir.prompt_sources",
    )
    domain_pack.bind_domain_bundle(bundle)
    return bundle
