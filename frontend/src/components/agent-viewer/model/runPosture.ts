import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import type { NormalizedHitlPrompt, OutcomeView, ViewerRunPosture } from './viewTypes';
import { isTerminalViewerRunStatus } from './snapshotModel';
import { firstText } from './modelUtils';

export function deriveRunPosture(input: {
  loading: boolean;
  error: string | null;
  connected: boolean;
  snapshot: AgentViewerSnapshot | null;
  activeHitl: NormalizedHitlPrompt | null;
}): ViewerRunPosture {
  if (input.loading) return 'loading';
  if (input.error) return 'error';
  if (!input.snapshot) return 'idle';
  if (input.activeHitl?.blocking) return 'waiting_user';
  const status = firstText(input.snapshot.run?.status).toLowerCase();
  if (isTerminalViewerRunStatus(status)) return 'terminal';
  if (!input.connected) return 'disconnected';
  if (['running', 'working', 'active'].includes(status)) return 'working';
  return 'working';
}

export function buildOutcomeView(snapshot: AgentViewerSnapshot | null): OutcomeView {
  if (!snapshot) {
    return { status: null, reason: null, isTerminal: false, summary: null };
  }
  const status = firstText(snapshot.run?.status) || null;
  const reason = firstText(snapshot.run?.reason) || null;
  const isTerminal = isTerminalViewerRunStatus(status);
  const summary = isTerminal ? firstText(reason, status) || null : null;
  return { status, reason, isTerminal, summary };
}
