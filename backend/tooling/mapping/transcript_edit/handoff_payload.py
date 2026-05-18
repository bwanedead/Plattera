"""Mechanical handoff-payload validation for transcript-edit published outputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from typing import Any

REQUIRED_HANDOFF_PAYLOAD_KEYS: tuple[str, ...] = (
    "source_transcript_verbatim",
    "normalized_or_mapping_transcript",
    "issues",
    "parcel_metadata",
    "hitl_decisions",
    "evidence_refs",
)

OPTIONAL_EMPTY_WITH_REASON_KEYS: dict[str, str] = {
    "issues": "issues_none_reason",
    "hitl_decisions": "hitl_decisions_none_reason",
    "evidence_refs": "evidence_refs_none_reason",
}

_HANDOFF_METADATA_SCHEMA_VERSION = 1


def validate_publish_handoff_payload(payload: Any) -> list[dict[str, Any]]:
    """Return mechanical shape errors that make a transcript-edit output unpublishable.

    This intentionally validates presence and explicitness only.  It does not
    infer whether the agent-authored metadata is semantically correct.
    """

    if not isinstance(payload, Mapping):
        return [
            {
                "code": "payload_not_mapping",
                "path": "payload",
                "message": "published transcript-edit revision payload must be an object",
            }
        ]

    errors: list[dict[str, Any]] = []
    for key in REQUIRED_HANDOFF_PAYLOAD_KEYS:
        if key not in payload:
            errors.append(
                {
                    "code": "required_handoff_key_missing",
                    "path": f"payload.{key}",
                    "message": f"required transcript-edit handoff payload key is missing: {key}",
                }
            )

    for key in ("source_transcript_verbatim", "normalized_or_mapping_transcript", "parcel_metadata"):
        if key in payload and not _has_material_content(payload.get(key)):
            errors.append(
                {
                    "code": "required_handoff_value_empty",
                    "path": f"payload.{key}",
                    "message": f"required transcript-edit handoff payload key is empty: {key}",
                }
            )

    for key, reason_key in OPTIONAL_EMPTY_WITH_REASON_KEYS.items():
        if key not in payload:
            continue
        if _has_material_content(payload.get(key)):
            continue
        if not _none_reason(payload, reason_key):
            errors.append(
                {
                    "code": "empty_handoff_lane_missing_none_reason",
                    "path": f"payload.{key}",
                    "message": (
                        f"payload.{key} is empty; add payload.{reason_key} to state why "
                        "the lane is intentionally empty"
                    ),
                }
            )

    return errors


def build_output_handoff_metadata(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Copy agent-authored handoff metadata lanes into the output wrapper."""

    none_reasons = {
        lane: reason
        for lane, reason_key in OPTIONAL_EMPTY_WITH_REASON_KEYS.items()
        if (reason := _none_reason(payload, reason_key))
    }
    return {
        "schema_version": _HANDOFF_METADATA_SCHEMA_VERSION,
        "payload_path": "revision_snapshot.payload",
        "source_transcript_verbatim_path": "revision_snapshot.payload.source_transcript_verbatim",
        "normalized_or_mapping_transcript_path": (
            "revision_snapshot.payload.normalized_or_mapping_transcript"
        ),
        "issues": deepcopy(payload.get("issues")),
        "parcel_metadata": deepcopy(payload.get("parcel_metadata")),
        "hitl_decisions": deepcopy(payload.get("hitl_decisions")),
        "evidence_refs": deepcopy(payload.get("evidence_refs")),
        "none_reasons": none_reasons,
    }


def _none_reason(payload: Mapping[str, Any], reason_key: str) -> str | None:
    value = payload.get(reason_key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _has_material_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        if not value:
            return False
        text = value.get("text")
        if isinstance(text, str):
            return bool(text.strip())
        return True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return len(value) > 0
    return True
