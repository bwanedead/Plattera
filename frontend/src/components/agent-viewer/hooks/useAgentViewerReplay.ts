import React from 'react';
import type { AgentViewerEvent, AgentViewerSnapshot } from '../../../services/agentViewerApi';
import {
  normalizeReplayBundleToSnapshot,
  replayEventsUpToTurn,
} from '../model/normalizeReplay';
import type { ArtifactLoadResult } from '../model/artifactLoadResult';
import { loadReplayArtifact } from '../transport/replay/replayArtifactGateway';
import {
  findTurnEntry,
  loadReplayBundle,
  loadReplayTurnSnapshot,
} from '../transport/replay/replayLoader';
import type { ReplayBundle } from '../transport/replay/replayTypes';
import { DEFAULT_REPLAY_FIXTURE_ID } from '../constants';

export type ReplayPlaybackState = {
  currentTurn: number;
  maxTurn: number;
  isPlaying: boolean;
};

export type UseAgentViewerReplayResult = {
  bundle: ReplayBundle | null;
  loading: boolean;
  error: string | null;
  snapshot: AgentViewerSnapshot | null;
  events: AgentViewerEvent[];
  playback: ReplayPlaybackState;
  play: () => void;
  pause: () => void;
  stepForward: () => void;
  stepBackward: () => void;
  scrubToTurn: (turn: number) => void;
  restart: () => void;
  loadArtifact: (ref: string) => Promise<ArtifactLoadResult>;
};

const DEFAULT_TICK_MS = 1200;

export function useAgentViewerReplay(
  fixtureId: string = DEFAULT_REPLAY_FIXTURE_ID,
  enabled = true,
): UseAgentViewerReplayResult {
  const [bundle, setBundle] = React.useState<ReplayBundle | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [currentTurn, setCurrentTurn] = React.useState(0);
  const [isPlaying, setIsPlaying] = React.useState(false);
  const [turnSnapshot, setTurnSnapshot] = React.useState<Record<string, unknown> | null>(null);

  React.useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    loadReplayBundle(fixtureId)
      .then((loaded) => {
        if (cancelled) return;
        setBundle(loaded);
        setCurrentTurn(0);
        setIsPlaying(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : 'Failed to load replay bundle');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, fixtureId]);

  const maxTurn = bundle?.manifest.source.turn_count ?? 0;

  React.useEffect(() => {
    if (!bundle || currentTurn <= 0) {
      setTurnSnapshot(null);
      return;
    }
    const entry = findTurnEntry(bundle, currentTurn);
    if (!entry) {
      setTurnSnapshot(null);
      return;
    }
    let cancelled = false;
    loadReplayTurnSnapshot(bundle.baseUrl, entry)
      .then((snapshot) => {
        if (!cancelled) setTurnSnapshot(snapshot);
      })
      .catch(() => {
        if (!cancelled) setTurnSnapshot(null);
      });
    return () => {
      cancelled = true;
    };
  }, [bundle, currentTurn]);

  React.useEffect(() => {
    if (!isPlaying || !bundle) return;
    if (currentTurn >= maxTurn) {
      setIsPlaying(false);
      return;
    }
    const timer = window.setTimeout(() => {
      setCurrentTurn((prev) => Math.min(prev + 1, maxTurn));
    }, DEFAULT_TICK_MS);
    return () => window.clearTimeout(timer);
  }, [bundle, currentTurn, isPlaying, maxTurn]);

  const snapshot = React.useMemo(() => {
    if (!bundle) return null;
    return normalizeReplayBundleToSnapshot(bundle, {
      turnIndex: currentTurn || undefined,
      turnSnapshot,
    });
  }, [bundle, currentTurn, turnSnapshot]);

  const events = React.useMemo(() => {
    if (!bundle || currentTurn <= 0) return [];
    return replayEventsUpToTurn(bundle, currentTurn);
  }, [bundle, currentTurn]);

  const loadArtifact = React.useCallback(
    async (ref: string) => {
      if (!bundle) {
        return { kind: 'unresolved' as const, ref, reason: 'Replay bundle not loaded' };
      }
      return loadReplayArtifact(bundle, ref);
    },
    [bundle],
  );

  return {
    bundle,
    loading,
    error,
    snapshot,
    events,
    playback: {
      currentTurn,
      maxTurn,
      isPlaying,
    },
    play: () => {
      if (currentTurn >= maxTurn) setCurrentTurn(0);
      setIsPlaying(true);
    },
    pause: () => setIsPlaying(false),
    stepForward: () => setCurrentTurn((prev) => Math.min(prev + 1, maxTurn)),
    stepBackward: () => {
      setIsPlaying(false);
      setCurrentTurn((prev) => Math.max(prev - 1, 0));
    },
    scrubToTurn: (turn: number) => {
      setIsPlaying(false);
      setCurrentTurn(Math.max(0, Math.min(turn, maxTurn)));
    },
    restart: () => {
      setIsPlaying(false);
      setCurrentTurn(0);
    },
    loadArtifact,
  };
}
