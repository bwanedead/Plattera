"""Agent-visible JSON Schema for finalize_current_deed_to_ir_output."""

from __future__ import annotations

from typing import Any

from domains.mapping.deed_to_ir.payloads.finalization_vocabulary import (
    ALLOWED_CORRECTION_DISPOSITIONS,
    ALLOWED_DEPENDENCY_DISPOSITIONS,
    ALLOWED_SCOPE_STATUSES,
)
from domains.mapping.deed_to_ir.payloads.published_output import MAX_RATIONALE_LENGTH


def build_finalize_current_deed_to_ir_output_request_json_shape() -> dict[str, Any]:
    """Compact decision maps only — no artifact refs or administrative rows."""
    return {
        "type": "object",
        "properties": {
            "scope_statuses": {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "enum": list(ALLOWED_SCOPE_STATUSES),
                },
            },
            "correction_dispositions": {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "enum": list(ALLOWED_CORRECTION_DISPOSITIONS),
                },
            },
            "dependency_dispositions": {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "enum": list(ALLOWED_DEPENDENCY_DISPOSITIONS),
                },
            },
            "rationales": {
                "type": "object",
                "additionalProperties": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": MAX_RATIONALE_LENGTH,
                },
            },
        },
        "additionalProperties": False,
    }


def build_finalize_current_deed_to_ir_output_example_request() -> dict[str, Any]:
    return {
        "scope_statuses": {
            "parcel_1": "handoffable",
            "parcel_2": "blocked",
        },
        "correction_dispositions": {
            "p1_call2_distance": "confirmed_source_repair",
        },
        "dependency_dispositions": {
            "parcel_2_continuation_scope": "include",
        },
        "rationales": {},
    }
