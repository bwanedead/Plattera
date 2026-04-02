"""Domain-owned adapter registry keyed by opaque domain id."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping, Protocol, runtime_checkable

from harness.runtime.composition import TurnSurface


@runtime_checkable
class DomainRuntimeAdapter(Protocol):
    """Generic surface-only adapter returned by a domain-owned factory."""

    domain_id: str

    def build_turn_surface(self, launch_context: Mapping[str, Any]) -> TurnSurface: ...


DomainAdapterFactory = Callable[[], DomainRuntimeAdapter]


@dataclass(frozen=True)
class DomainAdapterRegistration:
    domain_id: str
    adapter_factory: DomainAdapterFactory


class DomainAdapterLookupError(KeyError):
    """Raised when a requested domain adapter is not registered."""


class DomainAdapterRegistry:
    """Small registry seam for lazy adapter lookup by opaque domain id."""

    def __init__(self, registrations: Iterable[DomainAdapterRegistration] | None = None) -> None:
        self._registrations: dict[str, DomainAdapterRegistration] = {}
        for registration in registrations or ():
            self.register(registration)

    def register(self, registration: DomainAdapterRegistration) -> None:
        domain_id = _normalize_domain_id(registration.domain_id)
        if domain_id in self._registrations:
            raise ValueError(f"domain_adapter_already_registered:{domain_id}")
        self._registrations[domain_id] = DomainAdapterRegistration(
            domain_id=domain_id,
            adapter_factory=registration.adapter_factory,
        )

    def resolve_factory(self, domain_id: str) -> DomainAdapterFactory | None:
        registration = self._registrations.get(_normalize_domain_id(domain_id))
        if registration is None:
            return None
        return registration.adapter_factory

    def resolve(self, domain_id: str) -> DomainRuntimeAdapter | None:
        factory = self.resolve_factory(domain_id)
        if factory is None:
            return None
        return factory()

    def require_factory(self, domain_id: str) -> DomainAdapterFactory:
        normalized = _normalize_domain_id(domain_id)
        factory = self.resolve_factory(normalized)
        if factory is None:
            raise DomainAdapterLookupError(f"domain_adapter_not_registered:{normalized}")
        return factory

    def require(self, domain_id: str) -> DomainRuntimeAdapter:
        normalized = _normalize_domain_id(domain_id)
        adapter = self.resolve(normalized)
        if adapter is None:
            raise DomainAdapterLookupError(f"domain_adapter_not_registered:{normalized}")
        return adapter

    def iter_registrations(self) -> tuple[DomainAdapterRegistration, ...]:
        return tuple(self._registrations.values())


def _normalize_domain_id(raw: object) -> str:
    domain_id = str(raw or "").strip()
    if not domain_id:
        raise ValueError("domain_id_required")
    return domain_id
