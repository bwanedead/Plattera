import type { AgentViewerEvent, AgentViewerSnapshot } from '../../../services/agentViewerApi';
import { firstText, isRecord } from './modelUtils';
import type { ReplayBundle, ReplayTurnIndexEntry } from '../transport/replay/replayTypes';

export type TurnTelemetryRow = {
  turnIndex: number;
  durationSeconds: number | null;
  model: string | null;
  provider: string | null;
  tokenUsage: Record<string, number>;
  delegateActionCount: number;
  posture: string | null;
};

export type ObservabilityView = {
  rows: TurnTelemetryRow[];
  totalDurationSeconds: number;
  totalTokens: number;
  delegateEventCount: number;
  activeTurn: number | null;
};

function countDelegateActions(actions: unknown): number {
  if (!Array.isArray(actions)) return 0;
  return actions.filter((entry) => {
    if (!isRecord(entry)) return false;
    const actionType = firstText(entry.action_type, entry.tool_id, entry.alias).toLowerCase();
    return actionType.includes('delegate');
  }).length;
}

function turnEntryToRow(entry: ReplayTurnIndexEntry): TurnTelemetryRow {
  return {
    turnIndex: entry.turn_index,
    durationSeconds: typeof entry.duration_seconds === 'number' ? entry.duration_seconds : null,
    model: entry.model ?? null,
    provider: entry.provider ?? null,
    tokenUsage: entry.token_usage ?? {},
    delegateActionCount: countDelegateActions(entry.actions),
    posture: entry.motion_posture ?? entry.tool_execution_state ?? null,
  };
}

function eventDelegateSignal(event: AgentViewerEvent): number {
  const payload = event.payload;
  if (!isRecord(payload)) return 0;
  const fromActions = countDelegateActions(payload.actions);
  if (fromActions > 0) return fromActions;
  const eventType = event.event_type.toLowerCase();
  if (eventType.includes('delegate')) return 1;
  const summary = payload.summary;
  if (isRecord(summary) && firstText(summary.delegate_subtask, summary.tool_id).toLowerCase().includes('delegate')) {
    return 1;
  }
  return 0;
}

export function buildObservabilityView(
  snapshot: AgentViewerSnapshot | null,
  events: AgentViewerEvent[],
  replayBundle: ReplayBundle | null = null,
  currentTurn: number | null = null,
): ObservabilityView {
  let rows: TurnTelemetryRow[] = [];

  if (replayBundle) {
    const maxTurn = currentTurn && currentTurn > 0 ? currentTurn : replayBundle.manifest.source.turn_count;
    rows = replayBundle.turnIndex
      .filter((entry) => entry.turn_index <= maxTurn)
      .map(turnEntryToRow);
  } else {
    const byTurn = new Map<number, TurnTelemetryRow>();
    for (const event of events) {
      const turn = event.payload?.turn_index;
      if (typeof turn !== 'number') continue;
      const existing =
        byTurn.get(turn) ||
        ({
          turnIndex: turn,
          durationSeconds: null,
          model: null,
          provider: null,
          tokenUsage: {},
          delegateActionCount: 0,
          posture: event.status?.stage ?? null,
        } satisfies TurnTelemetryRow);
      existing.delegateActionCount += eventDelegateSignal(event);
      byTurn.set(turn, existing);
    }
    rows = [...byTurn.values()].sort((a, b) => a.turnIndex - b.turnIndex);
  }

  const totalDurationSeconds = rows.reduce((sum, row) => sum + (row.durationSeconds ?? 0), 0);
  const totalTokens = rows.reduce((sum, row) => {
    const total = row.tokenUsage.total;
    if (typeof total === 'number') return sum + total;
    return sum + Object.values(row.tokenUsage).reduce((inner, value) => inner + (typeof value === 'number' ? value : 0), 0);
  }, 0);
  const delegateEventCount = events.reduce((sum, event) => sum + eventDelegateSignal(event), 0);

  const replayTurn =
    snapshot?.run?.refs && isRecord(snapshot.run.refs) ? snapshot.run.refs.replay_turn : null;

  return {
    rows,
    totalDurationSeconds,
    totalTokens,
    delegateEventCount,
    activeTurn: typeof replayTurn === 'number' ? replayTurn : currentTurn,
  };
}
