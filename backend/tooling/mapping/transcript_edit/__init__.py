"""Transcript-edit dossier-backed tooling (filesystem, hydration; no domain orchestration)."""

from .draft_loading import (
    HydrateT0DraftsResult,
    HydratedT0Draft,
    hydrate_transcript_edit_working_draft,
    hydrate_t0_draft_refs,
)
from .draft_persistence import copy_forward_save, publish_transcript_edit_output, save_transcript_edit
from .image_loading import hydrate_source_image_context
from .startup_inventory import build_transcript_edit_startup_inventory

__all__ = [
    "HydrateT0DraftsResult",
    "HydratedT0Draft",
    "build_transcript_edit_startup_inventory",
    "copy_forward_save",
    "hydrate_source_image_context",
    "hydrate_t0_draft_refs",
    "hydrate_transcript_edit_working_draft",
    "publish_transcript_edit_output",
    "save_transcript_edit",
]
