"""Thin transcript-edit runtime adapter object for harness composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from harness.runtime.composition import TurnSurface
from harness.runtime.llm.streaming_config import STREAMING_RUN_CONTEXT_KEYS

from ..domain_pack import TranscriptEditDomainPack, build_transcript_edit_domain_pack
from ..manifest import TranscriptEditManifest
from ..payloads import TranscriptEditStartupInventory
from tooling.mapping.transcript_edit import build_transcript_edit_startup_inventory
from tooling.mapping.transcript_edit.dossier_startup_inventory import (
    DossierStartupInventoryBundle,
    build_dossier_transcript_edit_startup_inventory,
)
from tooling.mapping.transcript_edit.draft_persistence import resolve_workspace_key

from .composition import build_transcript_edit_turn_surface
from .dossier_composition import build_dossier_transcript_edit_turn_surface

_SCOPE_MODE_KEY = "transcript_edit_scope_mode"
_SCOPE_MODE_DOSSIER = "dossier"
_SCOPE_MODE_TRANSCRIPTION = "transcription"
_LEAF_SCOPE_KEYS = ("transcription_id", "segment_id")


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
        mode = _resolve_scope_mode(context)
        if mode == _SCOPE_MODE_DOSSIER:
            bundle = _build_dossier_startup_bundle(context)
            return build_dossier_transcript_edit_turn_surface(
                domain_pack=self.domain_pack,
                bundle=bundle,
            )
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


def _resolve_scope_mode(launch_context: Mapping[str, Any]) -> str:
    if _SCOPE_MODE_KEY not in launch_context:
        return _SCOPE_MODE_TRANSCRIPTION
    value = launch_context[_SCOPE_MODE_KEY]
    if type(value) is not str or value not in {_SCOPE_MODE_DOSSIER, _SCOPE_MODE_TRANSCRIPTION}:
        raise ValueError("transcript_edit_scope_mode_invalid")
    return value


def _build_dossier_startup_bundle(
    launch_context: Mapping[str, Any],
) -> DossierStartupInventoryBundle:
    _reject_dossier_leaf_scope(launch_context)
    dossier_id = _exact_required_text(launch_context, "dossier_id")
    workspace_id = _exact_optional_text(launch_context, "workspace_id")
    run_id = _exact_optional_text(launch_context, "run_id")
    workspace_key = resolve_workspace_key(workspace_id=workspace_id, run_id=run_id)
    if not workspace_key:
        raise ValueError("dossier_runtime_workspace_required")
    return build_dossier_transcript_edit_startup_inventory(
        dossier_id=dossier_id,
        workspace_id=workspace_id,
        run_id=run_id,
    )


def _reject_dossier_leaf_scope(launch_context: Mapping[str, Any]) -> None:
    for key in _LEAF_SCOPE_KEYS:
        if key not in launch_context:
            continue
        value = launch_context[key]
        if value is None:
            continue
        if type(value) is not str:
            raise ValueError("transcript_edit_dossier_leaf_scope_conflict")
        if value.strip():
            raise ValueError("transcript_edit_dossier_leaf_scope_conflict")


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


def _exact_required_text(mapping: Mapping[str, Any], key: str) -> str:
    if key not in mapping or mapping[key] is None:
        raise ValueError(f"{key}_required")
    value = mapping[key]
    if type(value) is not str:
        raise ValueError(f"{key}_invalid_type")
    text = value.strip()
    if not text:
        raise ValueError(f"{key}_required")
    return text


def _exact_optional_text(mapping: Mapping[str, Any], key: str) -> str | None:
    if key not in mapping or mapping[key] is None:
        return None
    value = mapping[key]
    if type(value) is not str:
        raise ValueError(f"{key}_invalid_type")
    text = value.strip()
    return text or None
