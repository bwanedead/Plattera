"""Identifier validation for Agent Viewer storage and stream keys."""

from __future__ import annotations

import re


class AgentViewerIdentifierError(ValueError):
    pass


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_viewer_identifier(value: str, field_name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise AgentViewerIdentifierError(f"{field_name}_required")
    if len(text) > 128:
        raise AgentViewerIdentifierError(f"{field_name}_too_long")
    if any(ord(ch) < 32 for ch in text):
        raise AgentViewerIdentifierError(f"{field_name}_invalid")
    if "/" in text or "\\" in text or ".." in text:
        raise AgentViewerIdentifierError(f"{field_name}_path_segment_invalid")
    if ":" in text:
        raise AgentViewerIdentifierError(f"{field_name}_stream_separator_forbidden")
    if not _IDENTIFIER_PATTERN.fullmatch(text):
        raise AgentViewerIdentifierError(f"{field_name}_invalid")
    return text


def validate_viewer_identifiers(*, loop_kind: str, run_id: str) -> tuple[str, str]:
    return (
        validate_viewer_identifier(loop_kind, "loop_kind"),
        validate_viewer_identifier(run_id, "run_id"),
    )
