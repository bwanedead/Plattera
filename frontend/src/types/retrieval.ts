export type PoolIdentifier = 'FINAL_SEGMENTS' | 'EVERYTHING';

export interface PoolOpenStatus {
  status: 'ok' | 'unavailable';
  reason_code: string | null;
  detail: string | null;
  action_hint: string | null;
}

export interface PoolHealthReport {
  active_vectors: number;
  tombstoned_vectors: number;
  tombstone_ratio: number;
  compact_recommended: boolean;
  compact_threshold: number;
}

export type SliceStatus = 'HEALTHY' | 'MISSING' | 'STALE_CONTENT' | 'STALE_IDENTITY' | 'UNAVAILABLE';

export interface SliceDiagnosis {
  dossier_id: string;
  entry_id: string;
  status: SliceStatus;
  reason: string;
  desired_signature?: string;
  indexed_signature?: string;
}

export interface DiagnosisCounts {
  healthy: number;
  missing: number;
  stale: number;
  unavailable: number;
}

export interface DiagnoseResponse {
  pool_identifier: string;
  pool_open: PoolOpenStatus;
  pool_health: PoolHealthReport | null;
  slice_diagnoses: SliceDiagnosis[] | null;
  counts: DiagnosisCounts;
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed';

export interface JobProgress {
  total: number;
  done: number;
  ok: number;
  failed: number;
}

export interface JobResult {
  dossier_id: string;
  entry_id: string;
  status: string;
  reason_code?: string;
  detail?: string;
}

export interface IndexJob {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  progress: JobProgress;
  results: JobResult[];
  results_returned: number;
  results_total: number;
  error?: string;
}

export type IndexMode = 'missing_only' | 'missing_and_stale';

export interface ExecuteIndexRequest {
  pool_identifier: PoolIdentifier;
  mode: IndexMode;
  limit?: number;
  dossier_id?: string;
  dry_run?: boolean;
}

export interface ExecuteIndexResponse {
  job_id: string;
  status: JobStatus;
}

export interface BootstrapIndexRequest {
  pool_identifier?: PoolIdentifier;
  force?: boolean;
}

export interface PoolBootstrapReport {
  status: string;
  reason_code: string | null;
  detail: string | null;
  action_hint: string | null;
}

export interface BootstrapPoolResult {
  pool_identifier: PoolIdentifier;
  bootstrap: PoolBootstrapReport;
  pool_open: PoolOpenStatus;
}

export interface BootstrapIndexResponse {
  results: BootstrapPoolResult[];
}
