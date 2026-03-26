from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CapabilityRequirement:
    """Shared declaration of what a domain pack needs."""

    capability_id: str
    required: bool = True
    category: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class DomainHandoffPosture:
    """Shared description of a pack's downstream handoff posture."""

    posture: str
    target_domain_id: str | None = None
    target_family_id: str | None = None
    reason_code: str | None = None
    summary: str | None = None
    domain_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainManifest:
    """Shared identity surface for a domain pack."""

    domain_id: str
    family_id: str
    display_name: str
    capability_requirements: tuple[CapabilityRequirement, ...] = field(default_factory=tuple)
    supported_handoffs: tuple[DomainHandoffPosture, ...] = field(default_factory=tuple)
    compatibility_status: str = "unknown"


@dataclass(frozen=True)
class DomainPackBundle:
    """Minimal shared bundle shape for a domain pack."""

    manifest: DomainManifest
    domain_pack: Any
    prompt_branch_source_ref: str | None = None


def build_domain_pack_bundle(
    *,
    manifest: DomainManifest,
    domain_pack: Any,
    prompt_branch_source_ref: str | None = None,
) -> DomainPackBundle:
    """Build the minimal shared bundle wrapper around a pack implementation."""

    return DomainPackBundle(
        manifest=manifest,
        domain_pack=domain_pack,
        prompt_branch_source_ref=prompt_branch_source_ref,
    )
