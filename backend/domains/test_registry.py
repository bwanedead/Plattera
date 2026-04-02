from __future__ import annotations

import pytest

from domains import (
    DomainAdapterLookupError,
    build_domain_adapter_registry,
    require_domain_adapter_factory,
)
from domains.mapping.transcript_edit.runtime_adapter import TranscriptEditRuntimeAdapter


def test_domain_registry_resolves_transcript_edit_by_domain_id() -> None:
    registry = build_domain_adapter_registry()

    adapter = registry.resolve("transcript_edit")

    assert adapter is not None
    assert isinstance(adapter, TranscriptEditRuntimeAdapter)
    assert adapter.domain_id == "transcript_edit"
    assert adapter.manifest.domain_id == "transcript_edit"
    assert registry.require("transcript_edit").domain_id == "transcript_edit"


def test_domain_registry_rejects_unknown_domain_id_explicitly() -> None:
    registry = build_domain_adapter_registry()

    with pytest.raises(DomainAdapterLookupError, match="domain_adapter_not_registered:unknown_domain"):
        registry.require_factory("unknown_domain")


def test_domain_registry_helper_matches_registry_lookup() -> None:
    factory = require_domain_adapter_factory("transcript_edit")
    adapter = factory()

    assert adapter.domain_id == "transcript_edit"
