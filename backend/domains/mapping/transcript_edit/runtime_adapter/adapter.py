"""Thin transcript-edit runtime adapter object for harness composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from harness.runtime.llm.streaming_config import STREAMING_RUN_CONTEXT_KEYS

from ..domain_pack import TranscriptEditDomainPack, build_transcript_edit_domain_pack
from ..manifest import TranscriptEditManifest
from ..payloads import TranscriptEditStartupInventory
from tooling.mapping.transcript_edit import build_transcript_edit_startup_inventory
from .composition import build_transcript_edit_turn_surface


@dataclass(frozen=True)
class TranscriptEditRuntimeAdapter:
    """Domain-owned adapter that only translates opaque launch context into a generic turn surface."""

    domain_pack: TranscriptEditDomainPack

    @property
    def domain_id(self) -> str:
        return self.manifest.domain_id

    @property
    def manifest(self) -> TranscriptEditManifest:
        return self.domain_pack.manifest

    def build_turn_surface(self, launch_context: Mapping[str, Any]) -> TurnSurface:
        context = _require_launch_context(launch_context)
        startup_inventory = _build_startup_inventory(context)
        return build_transcript_edit_turn_surface(
            domain_pack=self.domain_pack,
            startup_inventory=startup_inventory,
        )

    def enrich_launch_context(self, launch_context: Mapping[str, Any]) -> Mapping[str, Any]:
        """Inject transcript-edit scoped opaque run-context keys (mechanical caps/reminders)."""
        context = _require_launch_context(launch_context)
        out: dict[str, Any] = {}
        if "action_batch_policy" not in context:
            from ..execution.action_batch_policy import build_transcript_edit_action_batch_policy

            out["action_batch_policy"] = build_transcript_edit_action_batch_policy()
        if "delegate_observation_worklist_reminder" not in context:
            from ..execution.delegate_observation_reminder import (
                TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER,
            )

            out["delegate_observation_worklist_reminder"] = (
                TRANSCRIPT_EDIT_DELEGATE_OBSERVATION_REMINDER
            )
        if not any(key in context for key in STREAMING_RUN_CONTEXT_KEYS):
            out["llm_streaming"] = True
        return out


def build_transcript_edit_runtime_adapter() -> TranscriptEditRuntimeAdapter:
    """Lazy factory used by the domain adapter registry."""

    return TranscriptEditRuntimeAdapter(domain_pack=build_transcript_edit_domain_pack())


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
