import React from 'react';
import type { AgentViewerEvent, AgentViewerLoopKind, AgentViewerSnapshot } from '../../../services/agentViewerApi';
import { buildSnapshotView, mergeSnapshotAndLiveEvents, type AgentViewerSnapshotView } from '../model/snapshotModel';
import { createRegistryForSnapshot } from '../registry/domainAdapters';
import { useAgentViewerReplay } from './useAgentViewerReplay';
import { useAgentViewerSnapshot } from './useAgentViewerSnapshot';
import { useAgentViewerStream } from './useAgentViewerStream';
import { DEFAULT_REPLAY_FIXTURE_ID } from '../transport/replay/replayTypes';
import type { ReplayArtifactResult } from '../transport/replay/replayArtifactGateway';

export type AgentViewerTransportMode = 'live' | 'replay';

export type UseAgentViewerRunParams = {
  mode: AgentViewerTransportMode;
  isOpen?: boolean;
  loopKind?: AgentViewerLoopKind | null;
  runId?: string | null;
  replayFixtureId?: string;
};

export type AgentViewerRunView = {
  mode: AgentViewerTransportMode;
  snapshot: AgentViewerSnapshot | null;
  snapshotView: AgentViewerSnapshotView;
  events: AgentViewerEvent[];
  orderedEvents: AgentViewerEvent[];
  connected: boolean;
  loading: boolean;
  error: string | null;
  refreshSnapshot: () => void;
  loadArtifact?: (ref: string) => Promise<ReplayArtifactResult>;
  replay?: ReturnType<typeof useAgentViewerReplay>;
};

export function useAgentViewerRun({
  mode,
  isOpen = true,
  loopKind = null,
  runId = null,
  replayFixtureId = DEFAULT_REPLAY_FIXTURE_ID,
}: UseAgentViewerRunParams): AgentViewerRunView {
  const activeLoopKind = loopKind ?? null;
  const activeRunId = typeof runId === 'string' && runId.trim() ? runId : null;
  const hasLiveRun = mode === 'live' && Boolean(activeLoopKind && activeRunId);

  const replay = useAgentViewerReplay(replayFixtureId, mode === 'replay' && isOpen);

  const {
    snapshot: liveSnapshot,
    snapshotView: liveSnapshotView,
    snapshotLoading,
    snapshotError,
    refreshSnapshot,
  } = useAgentViewerSnapshot({
    isOpen: isOpen && hasLiveRun,
    activeLoopKind,
    activeRunId,
  });

  const {
    events: liveEvents,
    connected,
    connectionEpoch,
  } = useAgentViewerStream({
    isOpen: isOpen && hasLiveRun,
    activeLoopKind,
    activeRunId,
  });

  React.useEffect(() => {
    if (!hasLiveRun) return;
    if (connectionEpoch <= 0) return;
    refreshSnapshot();
  }, [connectionEpoch, hasLiveRun, refreshSnapshot]);

  const snapshot = mode === 'replay' ? replay.snapshot : liveSnapshot;
  const registry = React.useMemo(() => createRegistryForSnapshot(snapshot), [snapshot]);
  const snapshotView = React.useMemo(
    () => (mode === 'replay' ? buildSnapshotView(snapshot, registry) : liveSnapshotView),
    [liveSnapshotView, mode, registry, snapshot],
  );

  const events = mode === 'replay' ? replay.events : liveEvents;
  const orderedEvents = React.useMemo(() => {
    const merged = mergeSnapshotAndLiveEvents(snapshotView.activityEvents, events);
    const sorted = [...merged];
    sorted.sort((a, b) => {
      const at = typeof a.timestamp_epoch_seconds === 'number' ? a.timestamp_epoch_seconds : -1;
      const bt = typeof b.timestamp_epoch_seconds === 'number' ? b.timestamp_epoch_seconds : -1;
      if (at !== bt) return bt - at;
      const as = typeof a.seq === 'number' ? a.seq : -1;
      const bs = typeof b.seq === 'number' ? b.seq : -1;
      return bs - as;
    });
    return sorted;
  }, [events, snapshotView.activityEvents]);

  const loading = mode === 'replay' ? replay.loading : snapshotLoading;
  const error = mode === 'replay' ? replay.error : snapshotError;

  return {
    mode,
    snapshot,
    snapshotView,
    events,
    orderedEvents,
    connected: mode === 'replay' ? true : connected,
    loading,
    error,
    refreshSnapshot,
    loadArtifact: mode === 'replay' ? replay.loadArtifact : undefined,
    replay: mode === 'replay' ? replay : undefined,
  };
}
