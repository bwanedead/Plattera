import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import {
  defaultAgentViewerRegistry,
  type AgentViewerRegistry,
  type ViewerInventoryPresentation,
  type ViewerPrimitiveKind,
  type ViewerRegistryItem,
} from '../registry/viewerRegistry';

export type AgentViewerInventoryItem = ViewerInventoryPresentation & {
  id: string;
  primitive: ViewerPrimitiveKind;
  rendererId: string;
  ref?: string | null;
  raw: unknown;
};

export type AgentViewerInventorySection = {
  id: ViewerPrimitiveKind;
  title: string;
  count: number;
  items: AgentViewerInventoryItem[];
};

export function buildSnapshotInventory(
  snapshot: AgentViewerSnapshot | null,
  registry: AgentViewerRegistry = defaultAgentViewerRegistry,
): AgentViewerInventorySection[] {
  if (!snapshot) return emptySections();
  return [
    section('artifact', 'Artifacts', snapshot.artifacts.map((artifact) => resolveItem(registry, {
      primitive: 'artifact',
      id: artifact.ref,
      ref: artifact.ref,
      kind: artifact.kind,
      title: artifact.title,
      summary: artifact.summary,
      payload: {
        domain_hints: artifact.domain_hints || {},
        preview: artifact.preview || {},
      },
      raw: artifact,
    }))),
    section('evidence', 'Evidence', snapshot.evidence.map((evidence) => resolveItem(registry, {
      primitive: 'evidence',
      id: evidence.id,
      kind: evidence.kind,
      title: evidence.title,
      summary: evidence.artifact_refs?.[0] || null,
      payload: evidence.payload || {},
      raw: evidence,
    }))),
    section('work_item', 'Work Items', snapshot.work_items.map((workItem) => resolveItem(registry, {
      primitive: 'work_item',
      id: workItem.id,
      kind: workItem.status,
      title: workItem.title,
      status: workItem.status,
      summary: workItem.confidence || null,
      payload: workItem.domain_payload || {},
      raw: workItem,
    }))),
    section('hitl_prompt', 'HITL', snapshot.hitl_prompts.map((prompt) => resolveItem(registry, {
      primitive: 'hitl_prompt',
      id: prompt.prompt_id,
      kind: prompt.blocking ? 'blocking' : 'async',
      title: prompt.question,
      status: prompt.blocking ? 'blocking' : 'open',
      summary: prompt.choices?.slice(0, 3).join(', ') || null,
      payload: prompt.context || {},
      raw: prompt,
    }))),
    section('action', 'Actions', snapshot.actions.map((action) => resolveItem(registry, {
      primitive: 'action',
      id: action.id,
      kind: action.kind,
      title: action.label,
      status: action.disabled ? 'disabled' : 'available',
      summary: action.reason || null,
      payload: action.target || {},
      raw: action,
    }))),
  ];
}

function emptySections(): AgentViewerInventorySection[] {
  return [
    section('artifact', 'Artifacts', []),
    section('evidence', 'Evidence', []),
    section('work_item', 'Work Items', []),
    section('hitl_prompt', 'HITL', []),
    section('action', 'Actions', []),
  ];
}

function section(
  id: ViewerPrimitiveKind,
  title: string,
  items: AgentViewerInventoryItem[],
): AgentViewerInventorySection {
  return {
    id,
    title,
    count: items.length,
    items,
  };
}

function resolveItem(
  registry: AgentViewerRegistry,
  item: ViewerRegistryItem,
): AgentViewerInventoryItem {
  const resolved = registry.resolve(item);
  return {
    ...resolved.presentation,
    id: item.id,
    primitive: item.primitive,
    rendererId: resolved.registration.id,
    ref: item.ref || null,
    raw: item.raw,
  };
}
