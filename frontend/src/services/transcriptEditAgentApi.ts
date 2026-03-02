export interface TranscriptEditAgentRunRequest {
  dossier_id?: string;
  source_transcript_ref?: string;
  source_text?: string;
  source_image_refs?: string[];
  model?: string;
  max_iterations?: number;
  mode?: 'off' | 'audit_only' | 'audit_then_repair' | 'audit_then_repair_then_promote';
  auto_promote?: boolean;
  background?: boolean;
}

export interface TranscriptEditLiveStatus {
  timestamp_epoch_seconds?: number;
  iteration?: number;
  phase?: string;
  message?: string;
  execution_state?: string;
  latest_refs?: Record<string, any>;
  image_verification?: Record<string, any>;
}

export interface TranscriptEditRunSnapshot {
  run_id: string;
  status: 'running' | 'completed' | 'needs_review' | 'failed' | string;
  reason_code?: string | null;
  iterations?: number | null;
  session_id?: string | null;
  run_artifact_ref?: string | null;
  latest_refs?: Record<string, any> | null;
  review_required?: boolean;
  terminal_summary?: Record<string, any> | null;
  live_status?: TranscriptEditLiveStatus | null;
  progress_log?: TranscriptEditLiveStatus[] | null;
}

export interface TranscriptEditRunRecord {
  run_id: string;
  status: string;
  request?: Record<string, any>;
  created_at?: string;
  updated_at?: string;
  snapshot?: TranscriptEditRunSnapshot | null;
  error?: string | null;
}

const API_BASE =
  (typeof process !== 'undefined' &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE as string)) ||
  'http://127.0.0.1:8000';
const API_BASE_URL = `${API_BASE}/api/transcript-edit-agent`;

export const startTranscriptEditRun = async (
  request: TranscriptEditAgentRunRequest,
): Promise<{ run_id: string; status: string }> => {
  const response = await fetch(`${API_BASE_URL}/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      background: true,
      model: 'gpt-5.2',
      mode: 'audit_then_repair_then_promote',
      max_iterations: 4,
      auto_promote: true,
      ...request,
    }),
  });
  if (!response.ok) {
    throw new Error(`Transcript edit run start failed (${response.status})`);
  }
  return response.json();
};

export const getTranscriptEditRun = async (runId: string): Promise<TranscriptEditRunRecord> => {
  const response = await fetch(`${API_BASE_URL}/run/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    throw new Error(`Transcript edit run fetch failed (${response.status})`);
  }
  return response.json();
};

export const listTranscriptEditRuns = async (limit = 50): Promise<TranscriptEditRunRecord[]> => {
  const response = await fetch(`${API_BASE_URL}/runs?limit=${Math.max(1, Math.min(200, limit))}`);
  if (!response.ok) {
    throw new Error(`Transcript edit runs list failed (${response.status})`);
  }
  const payload = await response.json();
  const runs = Array.isArray(payload?.runs) ? payload.runs : [];
  return runs as TranscriptEditRunRecord[];
};
