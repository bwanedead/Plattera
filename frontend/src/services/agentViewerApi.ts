export type AgentViewerLoopKind =
  | 'mission_flow'
  | 'agent_loop'
  | 'transcript_edit';

export interface AgentViewerEventStatus {
  stage?: string;
  line1: string;
  line2?: string | null;
}

export interface AgentViewerArtifactRef {
  artifact_path: string;
}

export interface AgentViewerEvent {
  protocol: 'agent_viewer_event_v1';
  run_id: string;
  session_id?: string;
  loop_kind: AgentViewerLoopKind;
  lane?: string;
  lane_seq?: number | null;
  seq?: number | null;
  iteration?: number | null;
  timestamp_epoch_seconds?: number | null;
  event_type: string;
  status?: AgentViewerEventStatus;
  artifact_refs?: Record<string, AgentViewerArtifactRef>;
  payload?: Record<string, any>;
}

const API_BASE =
  (typeof process !== 'undefined' &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE as string)) ||
  'http://127.0.0.1:8000';

const API_BASE_URL = `${API_BASE}/api/agent-viewer`;

export const getAgentViewerEventsUrl = (loopKind: AgentViewerLoopKind, runId: string): string =>
  `${API_BASE_URL}/events/${encodeURIComponent(loopKind)}/${encodeURIComponent(runId)}`;

export const getAgentViewerArtifactImageUrl = (artifactRef: string): string =>
  `${API_BASE_URL}/artifact/image?artifact_ref=${encodeURIComponent(artifactRef)}`;

export const subscribeAgentViewerEvents = (
  loopKind: AgentViewerLoopKind,
  runId: string,
  onEvent: (event: AgentViewerEvent) => void,
  onError?: () => void,
): (() => void) => {
  const source = new EventSource(getAgentViewerEventsUrl(loopKind, runId));
  source.onmessage = (raw) => {
    try {
      const parsed = JSON.parse(raw.data || '{}') as AgentViewerEvent;
      if (!parsed || parsed.protocol !== 'agent_viewer_event_v1') return;
      onEvent(parsed);
    } catch {
      // Ignore malformed payload; stream remains active.
    }
  };
  source.onerror = () => {
    if (onError) onError();
  };
  return () => {
    try {
      source.close();
    } catch {
      // no-op
    }
  };
};

export const getAgentViewerArtifactJson = async (artifactRef: string): Promise<{ artifact_path: string; json: any }> => {
  const url = `${API_BASE_URL}/artifact/json?artifact_ref=${encodeURIComponent(artifactRef)}`;
  const response = await fetch(url);
  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = payload?.detail ? `: ${String(payload.detail)}` : '';
    } catch {
      // ignore parse failure; keep status-only message
    }
    throw new Error(`Failed to load artifact JSON (${response.status})${detail}`);
  }
  return response.json();
};

export interface AgentViewerFeedbackEntry {
  submitted_at_epoch_seconds: number;
  prompt_id?: string | null;
  choice?: string | null;
  note?: string | null;
  metadata?: Record<string, any>;
}

export const getAgentViewerFeedback = async (
  loopKind: AgentViewerLoopKind,
  runId: string,
): Promise<{ loop_kind: string; run_id: string; entries: AgentViewerFeedbackEntry[] }> => {
  const response = await fetch(
    `${API_BASE_URL}/feedback/${encodeURIComponent(loopKind)}/${encodeURIComponent(runId)}`,
  );
  if (!response.ok) {
    throw new Error(`Failed to load feedback (${response.status})`);
  }
  return response.json();
};

export const submitAgentViewerFeedback = async (
  loopKind: AgentViewerLoopKind,
  runId: string,
  payload: {
    prompt_id?: string | null;
    choice?: string | null;
    note?: string | null;
    metadata?: Record<string, any>;
  },
): Promise<{ ok: boolean; entry: AgentViewerFeedbackEntry; count: number }> => {
  const response = await fetch(
    `${API_BASE_URL}/feedback/${encodeURIComponent(loopKind)}/${encodeURIComponent(runId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  );
  if (!response.ok) {
    throw new Error(`Failed to submit feedback (${response.status})`);
  }
  return response.json();
};
