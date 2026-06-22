import type {
  AgentViewerAction,
  AgentViewerActivityEvent,
  AgentViewerArtifactDescriptor,
  AgentViewerEvent,
  AgentViewerSnapshot,
  AgentViewerWorkItem,
} from '../../../services/agentViewerApi';
import { firstText, isRecord } from './modelUtils';
import type {
  ReplayArtifactCatalogEntry,
  ReplayBundle,
  ReplayFinalState,
  ReplayManifest,
  ReplayStreamEvent,
  ReplayTurnIndexEntry,
} from '../transport/replay/replayTypes';

export function normalizeReplayBundleToSnapshot(
  bundle: ReplayBundle,
  options: {
    turnIndex?: number;
    turnSnapshot?: Record<string, unknown> | null;
  } = {},
): AgentViewerSnapshot {
  const { manifest, turnIndex, artifactCatalog, finalState } = bundle;
  const source = manifest.source;
  const atTurn = options.turnIndex ?? source.turn_count;
  const isTerminal = atTurn >= source.turn_count;
  const stateSource = pickStateSource(finalState, options.turnSnapshot, isTerminal);

  return {
    protocol: 'agent_viewer_snapshot_v1',
    run: {
      run_id: source.run_id,
      loop_kind: source.domain_id,
      status: isTerminal ? source.terminal_status : 'running',
      active_chapter_id: source.domain_id,
      started_at_epoch_seconds: turnIndex[0]?.started_at_epoch_seconds ?? null,
      updated_at_epoch_seconds: turnIndex[Math.min(atTurn, turnIndex.length) - 1]?.finished_at_epoch_seconds ?? null,
      reason: isTerminal ? source.terminal_decision ?? null : null,
      refs: {
        fixture_id: bundle.fixtureId,
        replay_turn: atTurn,
        product_refs: {
          dossier_id: source.dossier_id ?? null,
          transcription_id: source.transcription_id ?? null,
        },
      },
    },
    chapters: [
      {
        id: source.domain_id,
        title: titleCase(source.domain_id.replace(/_/g, ' ')),
        status: isTerminal ? source.terminal_status : 'running',
        artifact_refs: artifactCatalog.slice(0, 12).map((entry) => entry.ref_id),
      },
    ],
    activity: buildReplayActivity(bundle, atTurn),
    artifacts: normalizeArtifactCatalog(artifactCatalog),
    evidence: [],
    work_items: normalizeResolutionWorkItems(stateSource),
    hitl_prompts: [],
    actions: buildReplayActions(isTerminal),
  };
}

export function replayStreamEventToViewerEvent(
  manifest: ReplayManifest,
  streamEvent: ReplayStreamEvent,
  turnEntry: ReplayTurnIndexEntry | null,
): AgentViewerEvent {
  const line1 =
    firstText(turnEntry?.operator_progress_message, `Turn ${streamEvent.turn_index} completed`) ||
    streamEvent.event_type;
  const line2 = firstText(turnEntry?.rationale) || null;

  return {
    protocol: 'agent_viewer_event_v1',
    run_id: manifest.source.run_id,
    loop_kind: manifest.source.domain_id,
    lane: manifest.source.domain_id,
    lane_seq: streamEvent.turn_index,
    seq: streamEvent.sequence,
    iteration: streamEvent.turn_index,
    timestamp_epoch_seconds: streamEvent.occurred_at_epoch_seconds,
    event_type: streamEvent.event_type,
    status: {
      stage: firstText(turnEntry?.motion_posture, turnEntry?.tool_execution_state) || 'turn',
      line1,
      line2,
    },
    payload: {
      __replay: true,
      __view_id: `turn-event-${streamEvent.turn_index}`,
      turn_index: streamEvent.turn_index,
      payload_ref: streamEvent.payload_ref,
      summary: streamEvent.summary ?? {},
      motion_posture: turnEntry?.motion_posture ?? null,
      actions: turnEntry?.actions ?? [],
      terminal_decision: turnEntry?.terminal_decision ?? null,
      rationale: turnEntry?.rationale ?? null,
    },
  };
}

export function replayEventsUpToTurn(bundle: ReplayBundle, maxTurn: number): AgentViewerEvent[] {
  const turnByIndex = new Map(bundle.turnIndex.map((entry) => [entry.turn_index, entry]));
  return bundle.events
    .filter((event) => event.turn_index <= maxTurn)
    .map((event) =>
      replayStreamEventToViewerEvent(
        bundle.manifest,
        event,
        turnByIndex.get(event.turn_index) ?? null,
      ),
    );
}

function pickStateSource(
  finalState: ReplayFinalState,
  turnSnapshot: Record<string, unknown> | null | undefined,
  isTerminal: boolean,
): Record<string, unknown> {
  if (isTerminal) return finalState;
  if (!turnSnapshot) return finalState;
  return {
    mission_state: turnSnapshot.mission_state_after ?? turnSnapshot.mission_state ?? finalState.mission_state,
    resolution_state: turnSnapshot.resolution_state_after ?? turnSnapshot.resolution_state ?? finalState.resolution_state,
  };
}

function buildReplayActivity(bundle: ReplayBundle, atTurn: number): AgentViewerActivityEvent[] {
  return bundle.turnIndex
    .filter((entry) => entry.turn_index <= atTurn)
    .map((entry) => ({
      id: `turn-${entry.turn_index}`,
      title: firstText(entry.operator_progress_message, `Turn ${entry.turn_index}`) || `Turn ${entry.turn_index}`,
      timestamp_epoch_seconds: entry.finished_at_epoch_seconds ?? null,
      chapter_id: bundle.manifest.source.domain_id,
      detail: entry.rationale ?? null,
      status: firstText(entry.motion_posture, entry.tool_execution_state, 'completed') || 'completed',
      event_type: 'turn_completed',
      payload: {
        turn_index: entry.turn_index,
        actions: entry.actions ?? [],
        terminal_decision: entry.terminal_decision ?? null,
      },
    }));
}

function normalizeArtifactCatalog(catalog: ReplayArtifactCatalogEntry[]): AgentViewerArtifactDescriptor[] {
  return catalog.map((entry) => ({
    ref: entry.ref_id,
    kind: entry.kind,
    title: entry.ref_id,
    summary: entry.media_placeholder ? 'Media placeholder' : entry.kind,
    domain_hints: { occurrence_count: entry.occurrence_count ?? 0 },
    preview: entry.media_placeholder ? { media_placeholder: entry.media_placeholder } : {},
  }));
}

function normalizeResolutionWorkItems(stateSource: Record<string, unknown>): AgentViewerWorkItem[] {
  const resolution = stateSource.resolution_state;
  if (!isRecord(resolution)) return [];
  const items = Array.isArray(resolution.items) ? resolution.items : [];
  const out: AgentViewerWorkItem[] = [];

  for (const group of items) {
    if (!isRecord(group)) continue;
    const groupId = firstText(group.item_id, group.group_id, group.id) || `group-${out.length + 1}`;
    const groupTitle = firstText(group.title, group.label, groupId);
    out.push({
      id: groupId,
      title: groupTitle,
      status: firstText(group.status, group.blocking ? 'blocked' : 'open') || 'open',
      candidate_values: [],
      determined_value: group.closure_summary ?? null,
      confidence: null,
      blocker: group.blocking ? { blocking: true } : null,
      evidence_refs: [],
      relation_refs: [],
      domain_payload: { ...group, level: 'group' },
    });

    const units = Array.isArray(group.covered_units) ? group.covered_units : [];
    for (const unit of units) {
      if (!isRecord(unit)) continue;
      const unitId = firstText(unit.unit_id, unit.id) || `${groupId}-unit-${out.length}`;
      out.push({
        id: unitId,
        title: firstText(unit.title, unit.label, unitId),
        status: firstText(unit.status, 'open') || 'open',
        candidate_values: Array.isArray(unit.candidate_values) ? unit.candidate_values : [],
        determined_value: unit.determined_value ?? null,
        confidence: firstText(unit.determination) || null,
        blocker: unit.blocking ? { blocking: true } : null,
        evidence_refs: Array.isArray(unit.evidence_refs) ? unit.evidence_refs.map(String) : [],
        relation_refs: [groupId],
        domain_payload: { ...unit, parent_group_id: groupId, level: 'unit' },
      });
    }
  }

  return out.slice(0, 200);
}

function buildReplayActions(isTerminal: boolean): AgentViewerAction[] {
  if (!isTerminal) return [];
  return [
    {
      id: 'replay_restart',
      label: 'Restart replay',
      kind: 'viewer_command',
      target: { command: 'restart' },
    },
  ];
}

function titleCase(value: string): string {
  return value.replace(/\b\w/g, (char) => char.toUpperCase());
}
