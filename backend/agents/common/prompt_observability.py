"""Prompt observability scaffolding.

This module defines the first prompt-event metadata shape so prompt source
provenance can be carried alongside future call snapshots without waiting for
full persistence wiring.
"""

from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass, field
from typing import Any, Sequence

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class PromptSourceBlockRef:
    block_id: str
    layer: str
    owner: str
    source_path: str
    version: str
    content_hash: str


@dataclass(frozen=True)
class PromptEventMetadata:
    prompt_event_id: str | None = None
    run_link_id: str = ""
    run_id: str = ""
    iteration_index: int | None = None
    surface: str = ""
    domain: str = ""
    model: str = ""
    constitution_version: str = ""
    composition_mode: str = ""
    source_blocks: tuple[PromptSourceBlockRef, ...] = field(default_factory=tuple)
    structured_payload_keys: tuple[str, ...] = field(default_factory=tuple)


class PromptEventArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    metadata: PromptEventMetadata
    system_text: str = ""
    user_text: str = ""
    structured_payloads: dict[str, Any] = Field(default_factory=dict)
    model_output_payload: dict[str, Any] = Field(default_factory=dict)
    model_output_text: str | None = None
    parsed_output_summary: dict[str, Any] = Field(default_factory=dict)
    outcome_kind: str | None = Field(default=None, max_length=128)
    outcome_ref: str | None = Field(default=None, max_length=256)
    downstream_refs_delta: dict[str, Any] = Field(default_factory=dict)


def build_prompt_trace_payload(
    *,
    surface: str,
    domain: str,
    model: str,
    identity_source_blocks: Sequence[PromptSourceBlockRef],
    prompt_event_metadata: PromptEventMetadata | None,
    prompt_event: PromptEventArtifact | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "surface": str(surface or "").strip(),
        "domain": str(domain or "").strip(),
        "model": str(model or "").strip(),
        "prompt_event_metadata": asdict(prompt_event_metadata) if prompt_event_metadata is not None else None,
        "source_blocks": [asdict(block) for block in identity_source_blocks],
    }
    if prompt_event is not None:
        payload["prompt_event"] = prompt_event.model_dump(mode="json")
    return payload


def build_prompt_event_metadata(
    *,
    run_link_id: str,
    run_id: str = "",
    iteration_index: int | None = None,
    surface: str,
    domain: str,
    model: str,
    constitution_version: str,
    composition_mode: str,
    source_blocks: Sequence[PromptSourceBlockRef] = (),
    structured_payload_keys: Sequence[str] = (),
    prompt_event_id: str | None = None,
) -> PromptEventMetadata:
    resolved_run_link_id = str(run_link_id or "").strip()
    resolved_run_id = str(run_id or "").strip() or resolved_run_link_id
    resolved_surface = str(surface or "").strip()
    resolved_prompt_event_id = str(prompt_event_id or "").strip() or None
    if resolved_prompt_event_id is None and resolved_run_id and iteration_index is not None and resolved_surface:
        resolved_prompt_event_id = f"prompt_event:{resolved_run_id}:i{iteration_index:02d}:{resolved_surface}"
    return PromptEventMetadata(
        prompt_event_id=resolved_prompt_event_id,
        run_link_id=resolved_run_link_id,
        run_id=resolved_run_id,
        iteration_index=iteration_index,
        surface=resolved_surface,
        domain=str(domain or "").strip(),
        model=str(model or "").strip(),
        constitution_version=str(constitution_version or "").strip(),
        composition_mode=str(composition_mode or "").strip(),
        source_blocks=tuple(source_blocks),
        structured_payload_keys=tuple(str(key).strip() for key in structured_payload_keys if str(key).strip()),
    )


def build_prompt_event_artifact(
    *,
    metadata: PromptEventMetadata,
    system_text: str,
    user_text: str,
    structured_payloads: dict[str, Any] | None = None,
    model_output_payload: dict[str, Any] | None = None,
    model_output_text: str | None = None,
    parsed_output_summary: dict[str, Any] | None = None,
    outcome_kind: str | None = None,
    outcome_ref: str | None = None,
    downstream_refs_delta: dict[str, Any] | None = None,
) -> PromptEventArtifact:
    return PromptEventArtifact(
        metadata=metadata,
        system_text=str(system_text or ""),
        user_text=str(user_text or ""),
        structured_payloads=structured_payloads if isinstance(structured_payloads, dict) else {},
        model_output_payload=model_output_payload if isinstance(model_output_payload, dict) else {},
        model_output_text=(str(model_output_text) if isinstance(model_output_text, str) else None),
        parsed_output_summary=parsed_output_summary if isinstance(parsed_output_summary, dict) else {},
        outcome_kind=(str(outcome_kind).strip() if isinstance(outcome_kind, str) and outcome_kind.strip() else None),
        outcome_ref=(str(outcome_ref).strip() if isinstance(outcome_ref, str) and outcome_ref.strip() else None),
        downstream_refs_delta=downstream_refs_delta if isinstance(downstream_refs_delta, dict) else {},
    )
