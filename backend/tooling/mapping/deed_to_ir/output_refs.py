"""Canonical deed-to-IR output artifact refs."""

from __future__ import annotations

from .paths import UnsafeDeedToIrPathSegmentError, require_safe_revision_digits

OUTPUT_REF = "deed_to_ir:output"
OUTPUT_REV_PREFIX = "deed_to_ir:output:rev:"


def build_output_revision_ref(revision_digits: str) -> str:
    rev = require_safe_revision_digits(revision_digits)
    return f"{OUTPUT_REV_PREFIX}{rev}"


def parse_output_ref(ref_id: str) -> tuple[str, str | None]:
    text = str(ref_id or "").strip()
    if text == OUTPUT_REF:
        return "latest", None
    if text.startswith(OUTPUT_REV_PREFIX):
        suffix = text[len(OUTPUT_REV_PREFIX) :]
        try:
            return "revision", require_safe_revision_digits(suffix)
        except UnsafeDeedToIrPathSegmentError:
            return "invalid", None
    return "invalid", None
