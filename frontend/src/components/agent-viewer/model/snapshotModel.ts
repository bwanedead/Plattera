import type {
  AgentViewerActivityEvent,
  AgentViewerEvent,
  AgentViewerSnapshot,
} from '../../../services/agentViewerApi';
import { buildSnapshotInventory, type AgentViewerInventorySection } from './snapshotInventory';

export type AgentViewerSnapshotView = {
  snapshot: AgentViewerSnapshot | null;
  activityEvents: AgentViewerEvent[];
  runStatus: string | null;
  runReason: string | null;
  activityCount: number;
  artifactCount: number;
  evidenceCount: number;
  workItemCount: number;
  hitlPromptCount: number;
  inventorySections: AgentViewerInventorySection[];
};

export function buildSnapshotView(snapshot: AgentViewerSnapshot | null): AgentViewerSnapshotView {
  if (!snapshot) {
    return {
      snapshot: null,
      activityEvents: [],
      runStatus: null,
      runReason: null,
      activityCount: 0,
      artifactCount: 0,
      evidenceCount: 0,
      workItemCount: 0,
      hitlPromptCount: 0,
      inventorySections: [],
    };
  }
  return {
    snapshot,
    activityEvents: snapshot.activity.map((activity, idx) => activityToViewerEvent(snapshot, activity, idx)),
    runStatus: safeText(snapshot.run?.status) || null,
    runReason: safeText(snapshot.run?.reason) || null,
    activityCount: snapshot.activity.length,
    artifactCount: snapshot.artifacts.length,
    evidenceCount: snapshot.evidence.length,
    workItemCount: snapshot.work_items.length,
    hitlPromptCount: snapshot.hitl_prompts.length,
    inventorySections: buildSnapshotInventory(snapshot),
  };
}

export function mergeSnapshotAndLiveEvents(
  snapshotEvents: AgentViewerEvent[],
  liveEvents: AgentViewerEvent[],
): AgentViewerEvent[] {
  const out: AgentViewerEvent[] = [];
  const seen = new Set<string>();
  for (const evt of liveEvents) {
    out.push(evt);
    const key = eventDedupeKey(evt);
    if (key) seen.add(key);
  }
  for (const evt of snapshotEvents) {
    const key = eventDedupeKey(evt);
    if (key && seen.has(key)) continue;
    out.push(evt);
  }
  return out.slice(0, 300);
}

export function isTerminalViewerRunStatus(status: string | null | undefined): boolean {
  const normalized = safeText(status).toLowerCase();
  return ['completed', 'complete', 'failed', 'error', 'cancelled', 'canceled', 'blocked', 'handoff_ready', 'handed_off'].includes(normalized);
}

export function terminalStatusFromRunStatus(status: string | null | undefined): 'completed' | 'needs_review' | 'failed' | null {
  const normalized = safeText(status).toLowerCase();
  if (!normalized) return null;
  if (['completed', 'complete', 'handoff_ready', 'handed_off'].includes(normalized)) return 'completed';
  if (['failed', 'error', 'cancelled', 'canceled'].includes(normalized)) return 'failed';
  if (['blocked', 'partial', 'review_ready', 'needs_review'].includes(normalized)) return 'needs_review';
  return null;
}

function activityToViewerEvent(
  snapshot: AgentViewerSnapshot,
  activity: AgentViewerActivityEvent,
  idx: number,
): AgentViewerEvent {
  const run = snapshot.run;
  const eventType = firstText(activity.event_type, 'snapshot_activity');
  const payload = isRecord(activity.payload) ? activity.payload : {};
  const stage = firstText(activity.status, 'snapshot');
  const activityId = firstText(activity.id, `snapshot_activity_${idx + 1}`);
  return {
    protocol: 'agent_viewer_event_v1',
    loop_kind: run.loop_kind,
    run_id: run.run_id,
    lane: optionalText(activity.chapter_id),
    lane_seq: idx + 1,
    seq: idx + 1,
    iteration: null,
    timestamp_epoch_seconds: numberOrNull(activity.timestamp_epoch_seconds),
    event_type: eventType,
    status: {
      stage,
      line1: firstText(activity.title, eventType),
      line2: nullableText(activity.detail),
    },
    artifact_refs: artifactRefsFromPayload(payload),
    payload: {
      ...payload,
      __snapshot: true,
      snapshot_activity_id: activityId,
      phase: firstText(activity.status, payload.phase, 'snapshot'),
      stream_kind: firstText(payload.stream_kind, 'narration'),
    },
  };
}

function artifactRefsFromPayload(payload: Record<string, any>): Record<string, { artifact_path: string }> {
  const refs = payload.artifact_refs;
  if (!isRecord(refs)) return {};
  const out: Record<string, { artifact_path: string }> = {};
  for (const [key, value] of Object.entries(refs)) {
    if (isRecord(value) && typeof value.artifact_path === 'string' && value.artifact_path.trim()) {
      out[key] = { artifact_path: value.artifact_path.trim() };
    }
  }
  return out;
}

function eventDedupeKey(evt: AgentViewerEvent): string | null {
  const snapshotId = safeText(evt.payload?.snapshot_activity_id);
  if (snapshotId) return `snapshot:${snapshotId}`;
  const seq = typeof evt.seq === 'number' ? evt.seq : typeof evt.lane_seq === 'number' ? evt.lane_seq : null;
  if (seq !== null) return `${evt.loop_kind}:${evt.run_id}:${evt.event_type}:${seq}`;
  const ts = typeof evt.timestamp_epoch_seconds === 'number' ? evt.timestamp_epoch_seconds : null;
  const line1 = safeText(evt.status?.line1);
  if (ts !== null && line1) return `${evt.loop_kind}:${evt.run_id}:${evt.event_type}:${ts}:${line1}`;
  return null;
}

function safeText(value: any): string {
  return typeof value === 'string' ? value.trim() : '';
}

function firstText(...values: any[]): string {
  for (const value of values) {
    const text = safeText(value);
    if (text) return text;
  }
  return '';
}

function optionalText(value: any): string | undefined {
  const text = safeText(value);
  return text ? text : undefined;
}

function nullableText(value: any): string | null {
  const text = safeText(value);
  return text ? text : null;
}

function numberOrNull(value: any): number | null {
  return typeof value === 'number' ? value : null;
}

function isRecord(value: any): value is Record<string, any> {
  return Boolean(value && typeof value === 'object' && !Array.isArray(value));
}
