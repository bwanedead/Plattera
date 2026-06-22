import type { AgentViewerEvent } from '../../../services/agentViewerApi';

export function viewerEventIdentity(event: AgentViewerEvent): string {
  const viewId = event.payload?.__view_id;
  if (typeof viewId === 'string' && viewId.trim()) return viewId.trim();
  const turn = event.payload?.turn_index;
  if (typeof turn === 'number') return `turn-event-${turn}`;
  if (typeof event.seq === 'number') return `seq-${event.seq}`;
  return `${event.event_type}-${event.timestamp_epoch_seconds ?? 'na'}`;
}

export function viewerEventLabel(event: AgentViewerEvent): string {
  return event.status?.line1 || event.event_type;
}
