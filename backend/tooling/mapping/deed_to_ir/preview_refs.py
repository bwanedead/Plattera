"""Canonical deed-to-IR final package preview artifact refs."""

from __future__ import annotations

from .paths import UnsafeDeedToIrPathSegmentError, require_safe_revision_digits

PREVIEW_REF = "deed_to_ir:final_package_preview"
PREVIEW_REV_PREFIX = "deed_to_ir:final_package_preview:rev:"


def build_preview_revision_ref(revision_digits: str) -> str:
    rev = require_safe_revision_digits(revision_digits)
    return f"{PREVIEW_REV_PREFIX}{rev}"


def parse_preview_ref(ref_id: str) -> tuple[str, str | None]:
    text = str(ref_id or "").strip()
    if text == PREVIEW_REF:
        return "latest", None
    if text.startswith(PREVIEW_REV_PREFIX):
        suffix = text[len(PREVIEW_REV_PREFIX) :]
        try:
            return "revision", require_safe_revision_digits(suffix)
        except UnsafeDeedToIrPathSegmentError:
            return "invalid", None
    return "invalid", None
