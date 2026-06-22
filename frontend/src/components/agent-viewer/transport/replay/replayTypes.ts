/** Wire types for agent_run_replay.v1 bundles — viewer-owned, not harness schema. */

export type ReplayManifest = {
  schema_version: string;
  fixture_id: string;
  source: {
    domain_id: string;
    run_id: string;
    dossier_id?: string;
    transcription_id?: string;
    turn_count: number;
    terminal_status: string;
    terminal_decision?: string | null;
  };
  viewer_contract?: Record<string, unknown>;
  sanitization?: Record<string, unknown>;
};

export type ReplayTurnIndexEntry = {
  turn_index: number;
  file: string;
  started_at_epoch_seconds?: number;
  finished_at_epoch_seconds?: number;
  duration_seconds?: number;
  model?: string;
  provider?: string;
  operator_progress_message?: string | null;
  rationale?: string | null;
  actions?: Array<Record<string, unknown>>;
  tool_execution_state?: string | null;
  artifact_refs?: string[];
  motion_posture?: string | null;
  terminal_decision?: string | null;
  token_usage?: Record<string, number>;
};

export type ReplayStreamEvent = {
  schema_version: string;
  event_id: string;
  sequence: number;
  event_type: string;
  occurred_at_epoch_seconds: number;
  turn_index: number;
  payload_ref?: string;
  summary?: Record<string, unknown>;
  [key: string]: unknown;
};

export type ReplayArtifactCatalogEntry = {
  ref_id: string;
  kind: string;
  occurrence_count?: number;
  media_placeholder?: string | null;
};

export type ReplayMediaCatalogEntry = {
  ref_id: string;
  kind: string;
  role?: string;
  width_height?: [number, number] | null;
  original_byte_count?: number | null;
  descriptor_file?: string;
  placeholder_file?: string;
};

export type ReplayFinalState = {
  turn_index?: number;
  mission_state?: Record<string, unknown>;
  resolution_state?: Record<string, unknown>;
  stable_context_state?: Record<string, unknown>;
  terminal_decision?: string | null;
  [key: string]: unknown;
};

export type ReplayTurnSnapshot = Record<string, unknown>;

export type ReplayBundle = {
  fixtureId: string;
  baseUrl: string;
  manifest: ReplayManifest;
  turnIndex: ReplayTurnIndexEntry[];
  events: ReplayStreamEvent[];
  artifactCatalog: ReplayArtifactCatalogEntry[];
  mediaCatalog: ReplayMediaCatalogEntry[];
  finalState: ReplayFinalState;
};
