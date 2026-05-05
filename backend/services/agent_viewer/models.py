"""Generic Agent Viewer read-model contracts.

These models are intentionally domain-agnostic. Domain-specific meaning belongs
in opaque payloads or future domain viewer adapters, not in the shared shape.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


SNAPSHOT_PROTOCOL = "agent_viewer_snapshot_v1"


class AgentRun(BaseModel):
    run_id: str
    loop_kind: str
    status: str = "unknown"
    active_chapter_id: str | None = None
    started_at_epoch_seconds: int | None = None
    updated_at_epoch_seconds: int | None = None
    reason: str | None = None
    refs: dict[str, Any] = Field(default_factory=dict)


class RunChapter(BaseModel):
    id: str
    title: str
    status: str = "unknown"
    artifact_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


class ActivityEvent(BaseModel):
    id: str
    title: str
    timestamp_epoch_seconds: int | None = None
    chapter_id: str | None = None
    detail: str | None = None
    status: str = "info"
    event_type: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ArtifactDescriptor(BaseModel):
    ref: str
    kind: str = "unknown"
    title: str | None = None
    summary: str | None = None
    created_at_epoch_seconds: int | None = None
    domain_hints: dict[str, Any] = Field(default_factory=dict)
    preview: dict[str, Any] = Field(default_factory=dict)


class EvidencePacket(BaseModel):
    id: str
    kind: str = "unknown"
    title: str | None = None
    artifact_refs: list[str] = Field(default_factory=list)
    work_item_refs: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkItem(BaseModel):
    id: str
    title: str
    status: str = "unknown"
    candidate_values: list[Any] = Field(default_factory=list)
    determined_value: Any | None = None
    confidence: str | None = None
    blocker: dict[str, Any] | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    relation_refs: list[str] = Field(default_factory=list)
    domain_payload: dict[str, Any] = Field(default_factory=dict)


class HITLPrompt(BaseModel):
    prompt_id: str
    blocking: bool = False
    question: str
    choices: list[str] = Field(default_factory=list)
    note_enabled: bool = True
    evidence_refs: list[str] = Field(default_factory=list)
    affected_work_item_refs: list[str] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)


class ViewerAction(BaseModel):
    id: str
    label: str
    kind: str
    target: dict[str, Any] = Field(default_factory=dict)
    disabled: bool = False
    reason: str | None = None


class AgentViewerSnapshot(BaseModel):
    protocol: str = SNAPSHOT_PROTOCOL
    run: AgentRun
    chapters: list[RunChapter] = Field(default_factory=list)
    activity: list[ActivityEvent] = Field(default_factory=list)
    artifacts: list[ArtifactDescriptor] = Field(default_factory=list)
    evidence: list[EvidencePacket] = Field(default_factory=list)
    work_items: list[WorkItem] = Field(default_factory=list)
    hitl_prompts: list[HITLPrompt] = Field(default_factory=list)
    actions: list[ViewerAction] = Field(default_factory=list)


class FeedbackRequest(BaseModel):
    prompt_id: str | None = None
    choice: str | None = None
    note: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackListResponse(BaseModel):
    loop_kind: str
    run_id: str
    entries: list[dict[str, Any]] = Field(default_factory=list)
