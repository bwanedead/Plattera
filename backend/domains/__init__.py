"""Domain packs and adapter registry live here."""

from __future__ import annotations

from .mapping import build_mapping_domain_adapter_registry
from .registry import (
    DomainAdapterFactory,
    DomainAdapterLookupError,
    DomainAdapterRegistration,
    DomainAdapterRegistry,
    DomainRuntimeAdapter,
)


def build_domain_adapter_registry() -> DomainAdapterRegistry:
    """Build the domain-owned adapter registry without exposing internals."""

    registry = DomainAdapterRegistry()
    for registration in build_mapping_domain_adapter_registry().iter_registrations():
        registry.register(registration)
    return registry


def get_domain_adapter_factory(domain_id: str) -> DomainAdapterFactory | None:
    return build_domain_adapter_registry().resolve_factory(domain_id)


def require_domain_adapter_factory(domain_id: str) -> DomainAdapterFactory:
    return build_domain_adapter_registry().require_factory(domain_id)


__all__ = [
    "DomainAdapterFactory",
    "DomainAdapterLookupError",
    "DomainAdapterRegistration",
    "DomainAdapterRegistry",
    "DomainRuntimeAdapter",
    "build_domain_adapter_registry",
    "get_domain_adapter_factory",
    "require_domain_adapter_factory",
]
