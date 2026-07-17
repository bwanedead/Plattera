import type { AgentViewerWorkItem } from '../../../services/agentViewerApi';

export type ViewerRunPosture =
  | 'idle'
  | 'loading'
  | 'working'
  | 'waiting_user'
  | 'disconnected'
  | 'terminal'
  | 'error';

export type NormalizedHitlPrompt = {
  promptId: string;
  blocking: boolean;
  question: string;
  detail: string | null;
  choices: string[];
  evidenceRefs: string[];
  workItemRefs: string[];
  source: 'snapshot' | 'event';
  raw: unknown;
};

export type FeedbackLifecycleEntry = {
  submittedAt: number;
  promptId: string | null;
  choice: string | null;
  note: string | null;
  metadata: Record<string, unknown>;
};

export type WorkItemView = {
  id: string;
  title: string;
  status: string;
  candidateValues: unknown[];
  determinedValue: unknown | null;
  confidence: string | null;
  evidenceRefs: string[];
  relationRefs: string[];
  level: 'group' | 'unit' | 'item';
  parentId: string | null;
  domainPayload: Record<string, unknown>;
  raw: AgentViewerWorkItem;
};

export type OutcomeView = {
  status: string | null;
  reason: string | null;
  isTerminal: boolean;
  summary: string | null;
};
