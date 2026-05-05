export type AgentViewerLoopKind =
  | 'mission_flow'
  | 'agent_loop'
  | 'transcript_edit'
  | (string & {});

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

export interface AgentViewerRun {
  run_id: string;
  loop_kind: string;
  status: string;
  active_chapter_id?: string | null;
  started_at_epoch_seconds?: number | null;
  updated_at_epoch_seconds?: number | null;
  reason?: string | null;
  refs?: Record<string, any>;
}

export interface AgentViewerRunChapter {
  id: string;
  title: string;
  status: string;
  artifact_refs?: string[];
  evidence_refs?: string[];
  domain_payload?: Record<string, any>;
}

export interface AgentViewerActivityEvent {
  id: string;
  title: string;
  timestamp_epoch_seconds?: number | null;
  chapter_id?: string | null;
  detail?: string | null;
  status: string;
  event_type?: string | null;
  payload?: Record<string, any>;
}

export interface AgentViewerArtifactDescriptor {
  ref: string;
  kind: string;
  title?: string | null;
  summary?: string | null;
  created_at_epoch_seconds?: number | null;
  domain_hints?: Record<string, any>;
  preview?: Record<string, any>;
}

export interface AgentViewerEvidencePacket {
  id: string;
  kind: string;
  title?: string | null;
  artifact_refs?: string[];
  work_item_refs?: string[];
  payload?: Record<string, any>;
}

export interface AgentViewerWorkItem {
  id: string;
  title: string;
  status: string;
  candidate_values?: any[];
  determined_value?: any | null;
  confidence?: string | null;
  blocker?: Record<string, any> | null;
  evidence_refs?: string[];
  relation_refs?: string[];
  domain_payload?: Record<string, any>;
}

export interface AgentViewerHitlPrompt {
  prompt_id: string;
  blocking: boolean;
  question: string;
  choices?: string[];
  note_enabled?: boolean;
  evidence_refs?: string[];
  affected_work_item_refs?: string[];
  context?: Record<string, any>;
}

export interface AgentViewerAction {
  id: string;
  label: string;
  kind: string;
  target?: Record<string, any>;
  disabled?: boolean;
  reason?: string | null;
}

export interface AgentViewerSnapshot {
  protocol: 'agent_viewer_snapshot_v1';
  run: AgentViewerRun;
  chapters: AgentViewerRunChapter[];
  activity: AgentViewerActivityEvent[];
  artifacts: AgentViewerArtifactDescriptor[];
  evidence: AgentViewerEvidencePacket[];
  work_items: AgentViewerWorkItem[];
  hitl_prompts: AgentViewerHitlPrompt[];
  actions: AgentViewerAction[];
}

const API_BASE =
  (typeof process !== 'undefined' &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE as string)) ||
  'http://127.0.0.1:8000';

const API_BASE_URL = `${API_BASE}/api/agent-viewer`;

export const getAgentViewerEventsUrl = (loopKind: AgentViewerLoopKind, runId: string): string =>
  `${API_BASE_URL}/events/${encodeURIComponent(loopKind)}/${encodeURIComponent(runId)}`;

export const getAgentViewerSnapshot = async (
  loopKind: AgentViewerLoopKind,
  runId: string,
): Promise<AgentViewerSnapshot> => {
  const response = await fetch(
    `${API_BASE_URL}/snapshot/${encodeURIComponent(loopKind)}/${encodeURIComponent(runId)}`,
  );
  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = payload?.detail ? `: ${String(payload.detail)}` : '';
    } catch {
      // keep status-only message
    }
    throw new Error(`Failed to load Agent Viewer snapshot (${response.status})${detail}`);
  }
  return response.json();
};

export const getAgentViewerArtifactImageUrl = (artifactRef: string): string =>
  `${API_BASE_URL}/artifact/image?artifact_ref=${encodeURIComponent(artifactRef)}`;

export const subscribeAgentViewerEvents = (
  loopKind: AgentViewerLoopKind,
  runId: string,
  onEvent: (event: AgentViewerEvent) => void,
  onError?: () => void,
  onOpen?: () => void,
): (() => void) => {
  const source = new EventSource(getAgentViewerEventsUrl(loopKind, runId));
  source.onopen = () => {
    if (onOpen) onOpen();
  };
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
