"""Thin transcript-edit runtime adapter object for harness composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from domains.mapping.prompting import build_mapping_family_branch_blocks
from harness.runtime.composition import TurnSurface

from ..manifest import TranscriptEditManifest, build_transcript_edit_manifest
from ..payloads import TranscriptEditStartupInventory
from ..prompting import build_transcript_edit_branch_blocks
from ..prompting.surfaces.procedural_guidance import build_transcript_edit_procedural_guidance_blocks
from tooling.mapping.transcript_edit import build_transcript_edit_startup_inventory
from .composition import build_transcript_edit_turn_surface


@dataclass(frozen=True)
class TranscriptEditRuntimeAdapter:
    """Domain-owned adapter that only translates opaque launch context into a generic turn surface."""

    manifest: TranscriptEditManifest

    @property
    def domain_id(self) -> str:
        return self.manifest.domain_id

    def build_turn_surface(self, launch_context: Mapping[str, Any]) -> TurnSurface:
        context = _require_launch_context(launch_context)
        startup_inventory = _build_startup_inventory(context)
        prompt_blocks = (
            *build_mapping_family_branch_blocks(),
            *build_transcript_edit_branch_blocks(),
            *build_transcript_edit_procedural_guidance_blocks(),
        )
        return build_transcript_edit_turn_surface(
            prompt_blocks=prompt_blocks,
            startup_inventory=startup_inventory,
        )


def build_transcript_edit_runtime_adapter() -> TranscriptEditRuntimeAdapter:
    """Lazy factory used by the domain adapter registry."""

    return TranscriptEditRuntimeAdapter(manifest=build_transcript_edit_manifest())


def _build_startup_inventory(launch_context: Mapping[str, Any]) -> TranscriptEditStartupInventory:
    dossier_id = _required_text(launch_context, "dossier_id")
    transcription_id = _required_text(launch_context, "transcription_id")
    return build_transcript_edit_startup_inventory(
        dossier_id=dossier_id,
        transcription_id=transcription_id,
        segment_id=_optional_text(launch_context, "segment_id"),
        run_id=_optional_text(launch_context, "run_id"),
        workspace_id=_optional_text(launch_context, "workspace_id"),
    )


def _require_launch_context(raw: object) -> Mapping[str, Any]:
    if not isinstance(raw, Mapping):
        raise TypeError("launch_context_must_be_mapping")
    return raw


def _required_text(mapping: Mapping[str, Any], key: str) -> str:
    value = str(mapping.get(key) or "").strip()
    if not value:
        raise ValueError(f"{key}_required")
    return value


def _optional_text(mapping: Mapping[str, Any], key: str) -> str | None:
    value = str(mapping.get(key) or "").strip()
    return value or None
