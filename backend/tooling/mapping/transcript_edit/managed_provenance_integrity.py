"""Shared integrity seam: refuse save/copy that silently invalidate managed provenance."""

from __future__ import annotations

from typing import Any

from domains.mapping.transcript_edit.payloads.transcript_edit_decisions import (
    TRANSCRIPT_EDIT_DECISIONS_FIELD,
    TRANSCRIPT_EDIT_LANES,
)
from tooling.mapping.transcript_edit.transcript_edit_decisions_validate import (
    PersistedProvenanceError,
    managed_provenance_field_present,
    validate_persisted_transcript_edit_decisions,
)

__all__ = [
    "ManagedProvenanceIntegrityError",
    "assert_managed_provenance_coherent_for_save",
    "managed_provenance_field_present",
    "payload_has_managed_provenance",
]


class ManagedProvenanceIntegrityError(Exception):
    """Refuse a write that would silently break managed decision provenance."""

    def __init__(self, reason_code: str, detail: str = "") -> None:
        self.reason_code = str(reason_code)
        self.detail = str(detail or "")
        message = self.reason_code if not self.detail else f"{self.reason_code}: {self.detail}"
        super().__init__(message)


_REPAIR_HINT = (
    "Use apply_transcript_edits for evidence-linked transcript changes or "
    "provenance updates. Save/copy may only change unrelated metadata while "
    "preserving transcript lanes and transcript_edit_decisions unchanged."
)


def payload_has_managed_provenance(payload: Any) -> bool:
    """True when provenance field is present AND validates as current v1.

    Presence of a malformed field raises ManagedProvenanceIntegrityError —
    never treated as unmanaged.
    """
    if not managed_provenance_field_present(payload):
        return False
    try:
        validate_persisted_transcript_edit_decisions(payload=payload)
    except PersistedProvenanceError as exc:
        raise ManagedProvenanceIntegrityError(exc.reason_code, exc.detail) from exc
    return True


def assert_managed_provenance_coherent_for_save(
    *,
    previous_payload: dict[str, Any] | None,
    next_payload: dict[str, Any],
) -> None:
    """Refuse save/copy that would persist or silently break managed provenance.

    - Any present next provenance must fully validate (transport bounds included).
    - Historical drafts without the field remain writable.
    - Once prior managed provenance exists: lanes and decisions must be preserved.
    """
    if type(next_payload) is not dict:
        raise ManagedProvenanceIntegrityError(
            "managed_provenance_requires_apply_transcript_edits",
            "Next payload must be an object.",
        )

    # Fail closed on any present next provenance (including first introduction via save).
    if managed_provenance_field_present(next_payload):
        try:
            validate_persisted_transcript_edit_decisions(payload=next_payload)
        except PersistedProvenanceError as exc:
            raise ManagedProvenanceIntegrityError(exc.reason_code, exc.detail) from exc

    if previous_payload is None:
        return
    if not managed_provenance_field_present(previous_payload):
        return

    # Fail closed on malformed prior provenance.
    try:
        validate_persisted_transcript_edit_decisions(payload=previous_payload)
    except PersistedProvenanceError as exc:
        raise ManagedProvenanceIntegrityError(exc.reason_code, exc.detail) from exc

    for lane in TRANSCRIPT_EDIT_LANES:
        if lane not in previous_payload:
            continue
        prev = previous_payload[lane]
        nxt = next_payload.get(lane)
        if prev != nxt:
            raise ManagedProvenanceIntegrityError(
                "managed_provenance_requires_apply_transcript_edits",
                f"Transcript lane {lane!r} changed while managed provenance is present. {_REPAIR_HINT}",
            )

    prev_block = previous_payload.get(TRANSCRIPT_EDIT_DECISIONS_FIELD)
    next_block = next_payload.get(TRANSCRIPT_EDIT_DECISIONS_FIELD)
    if next_block is None:
        raise ManagedProvenanceIntegrityError(
            "managed_provenance_requires_apply_transcript_edits",
            f"Managed provenance was dropped. {_REPAIR_HINT}",
        )
    if prev_block != next_block:
        raise ManagedProvenanceIntegrityError(
            "managed_provenance_requires_apply_transcript_edits",
            f"Managed provenance was mutated outside apply_transcript_edits. {_REPAIR_HINT}",
        )
