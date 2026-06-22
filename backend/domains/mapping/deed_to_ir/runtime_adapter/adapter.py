"""Thin deed-to-IR runtime adapter object for harness composition."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from harness.runtime.composition import TurnSurface

from ..domain_pack import DeedToIrDomainPack, build_deed_to_ir_domain_pack
from ..manifest import DeedToIrManifest
from ..payloads import (
    DeedToIrScope,
    DeedToIrStartupHandoff,
)
from tooling.mapping.deed_to_ir import build_deed_to_ir_startup_handoff
from .composition import build_deed_to_ir_turn_surface


@dataclass(frozen=True)
class DeedToIrRuntimeAdapter:
    domain_pack: DeedToIrDomainPack

    @property
    def domain_id(self) -> str:
        return self.manifest.domain_id

    @property
    def manifest(self) -> DeedToIrManifest:
        return self.domain_pack.manifest

    def build_turn_surface(self, launch_context: Mapping[str, Any]) -> TurnSurface:
        context = _require_launch_context(launch_context)
        handoff = _build_startup_handoff(context)
        return build_deed_to_ir_turn_surface(
            domain_pack=self.domain_pack,
            startup_handoff=handoff,
        )

    def enrich_launch_context(self, launch_context: Mapping[str, Any]) -> Mapping[str, Any]:
        """No domain launch-context defaults are currently required."""
        del launch_context
        return {}


def build_deed_to_ir_runtime_adapter() -> DeedToIrRuntimeAdapter:
    return DeedToIrRuntimeAdapter(domain_pack=build_deed_to_ir_domain_pack())


def _build_startup_handoff(launch_context: Mapping[str, Any]) -> DeedToIrStartupHandoff:
    dossier_id = _required_text(launch_context, "dossier_id")
    scope = DeedToIrScope(
        dossier_id=dossier_id,
        run_id=_optional_text(launch_context, "run_id"),
        workspace_id=_optional_text(launch_context, "workspace_id"),
        transcription_id=_optional_text(launch_context, "transcription_id"),
    )
    output_path = _optional_text(launch_context, "transcript_edit_output_path")
    if not output_path:
        raise ValueError("transcript_edit_output_path_required")
    from tooling.mapping.deed_to_ir.resolution_state_loading import resolve_resolution_state_snapshot

    inline_snapshot = launch_context.get("resolution_state_snapshot")
    snapshot_dict = resolve_resolution_state_snapshot(
        resolution_state_snapshot=(
            dict(inline_snapshot) if isinstance(inline_snapshot, Mapping) else None
        ),
        resolution_state_snapshot_path=_optional_text(
            launch_context,
            "resolution_state_snapshot_path",
        ),
    )
    return build_deed_to_ir_startup_handoff(
        scope=scope,
        transcript_edit_output_path=output_path,
        resolution_state_ref=_optional_text(launch_context, "resolution_state_ref"),
        resolution_state_snapshot=snapshot_dict,
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
