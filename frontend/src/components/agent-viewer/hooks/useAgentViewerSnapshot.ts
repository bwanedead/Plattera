import React from 'react';
import {
  getAgentViewerSnapshot,
  type AgentViewerLoopKind,
  type AgentViewerSnapshot,
} from '../../../services/agentViewerApi';
import { buildSnapshotView } from '../model/snapshotModel';

type Params = {
  isOpen: boolean;
  activeLoopKind: AgentViewerLoopKind | null;
  activeRunId: string | null;
};

export function useAgentViewerSnapshot({ isOpen, activeLoopKind, activeRunId }: Params) {
  const [snapshot, setSnapshot] = React.useState<AgentViewerSnapshot | null>(null);
  const [snapshotLoading, setSnapshotLoading] = React.useState(false);
  const [snapshotError, setSnapshotError] = React.useState<string | null>(null);
  const [refreshIndex, setRefreshIndex] = React.useState(0);

  const refreshSnapshot = React.useCallback(() => {
    setRefreshIndex((value) => value + 1);
  }, []);

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) {
      setSnapshot(null);
      setSnapshotLoading(false);
      setSnapshotError(null);
      return;
    }
    let cancelled = false;
    setSnapshotLoading(true);
    setSnapshotError(null);
    (async () => {
      try {
        const payload = await getAgentViewerSnapshot(activeLoopKind, activeRunId);
        if (!cancelled) setSnapshot(payload);
      } catch (error) {
        if (!cancelled) {
          setSnapshot(null);
          setSnapshotError(error instanceof Error ? error.message : 'Failed to load Agent Viewer snapshot');
        }
      } finally {
        if (!cancelled) setSnapshotLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeLoopKind, activeRunId, refreshIndex]);

  const snapshotView = React.useMemo(() => buildSnapshotView(snapshot), [snapshot]);

  return {
    snapshot,
    snapshotView,
    snapshotLoading,
    snapshotError,
    refreshSnapshot,
  };
}
