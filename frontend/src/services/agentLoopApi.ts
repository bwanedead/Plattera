export interface AgentLoopRunRequest {
  dossier_id?: string;
  text?: string;
  model?: string;
  max_iterations?: number;
  requires_global_placement?: boolean;
  render_required?: boolean;
  background?: boolean;
}

export interface AgentLoopRunStartResponse {
  run_id: string;
  status: string;
  dossier_id?: string | null;
}

export interface AgentLoopRunSnapshot {
  run_id: string;
  request_id?: string;
  dossier_id?: string | null;
  model?: string | null;
  status: 'running' | 'completed' | 'failed' | string;
  session_id?: string | null;
  run_artifact_ref?: string | null;
  transcript_artifact_ref?: string | null;
  terminal?: any;
  dashboard?: any;
  error?: string | null;
  live_status?: AgentTapeStatus | null;
  last_agent_tape_event?: AgentTapeEvent | null;
}

export interface AgentTapeStatus {
  iteration?: number | null;
  stage?: string | null;
  phase?: string | null;
  action_type?: string | null;
  outcome?: string | null;
  reason_code?: string | null;
  status_chip?: string | null;
  display_delta?: string | null;
  artifact_refs?: Record<string, string> | null;
  line1?: string | null;
  line2?: string | null;
}

export interface AgentTapeEvent {
  event_type: 'agent_tape_update' | string;
  run_id?: string;
  seq?: number;
  timestamp_epoch_seconds?: number;
  source_event_type?: string;
  status?: AgentTapeStatus | null;
}

const API_BASE = (typeof process !== 'undefined' && process.env && (process.env.NEXT_PUBLIC_API_BASE as string)) || 'http://127.0.0.1:8000';
const API_BASE_URL = `${API_BASE}/api/agent-loop`;

export const startAgentLoopRun = async (request: AgentLoopRunRequest): Promise<AgentLoopRunStartResponse> => {
  const response = await fetch(`${API_BASE_URL}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      background: true,
      model: 'gpt-5.2',
      max_iterations: 12,
      ...request,
    }),
  });
  if (!response.ok) {
    throw new Error(`Agent loop start failed (${response.status})`);
  }
  return response.json();
};

export const getAgentLoopRun = async (runId: string): Promise<AgentLoopRunSnapshot> => {
  const response = await fetch(`${API_BASE_URL}/run/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(`Agent loop run fetch failed (${response.status})`);
  }
  return response.json();
};

export const openAgentLoopArtifact = async (artifactRef: string): Promise<any> => {
  const url = `${API_BASE_URL}/artifact/open?artifact_ref=${encodeURIComponent(artifactRef)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Agent loop artifact open failed (${response.status})`);
  }
  return response.json();
};

export const getAgentLoopArtifactJson = async (artifactRef: string): Promise<{ artifact_path: string; json: any }> => {
  const url = `${API_BASE_URL}/artifact/json?artifact_ref=${encodeURIComponent(artifactRef)}`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Agent loop artifact json failed (${response.status})`);
  }
  return response.json();
};

export const getAgentLoopEventsUrl = (runId: string): string => {
  return `${API_BASE_URL}/events/${encodeURIComponent(runId)}`;
};
