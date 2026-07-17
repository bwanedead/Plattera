import React from 'react';
import { subscribeAgentViewerEvents, type AgentViewerEvent, type AgentViewerLoopKind } from '../../../services/agentViewerApi';
import { postAgentViewerTimingLog } from '../transport/live/frontendLogGateway';
import { useAgentViewerClientLogBridge } from './useAgentViewerClientLogBridge';

type Params = {
  isOpen: boolean;
  activeLoopKind: AgentViewerLoopKind | null;
  activeRunId: string | null;
};

export function useAgentViewerStream({ isOpen, activeLoopKind, activeRunId }: Params) {
  const [events, setEvents] = React.useState<AgentViewerEvent[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [connectionEpoch, setConnectionEpoch] = React.useState(0);
  const [isHydratingReplay, setIsHydratingReplay] = React.useState(false);
  const replayHydratingRef = React.useRef(false);

  useAgentViewerClientLogBridge(isOpen);

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) return;
    const startedAtMs = Date.now();
    let firstEventLogged = false;
    let firstLiveLogged = false;
    let firstPromptLogged = false;
    void postAgentViewerTimingLog(`subscribe_start loop=${activeLoopKind} run=${activeRunId}`, {
      loop_kind: activeLoopKind,
      run_id: activeRunId,
    });
    setEvents([]);
    setConnected(false);
    setIsHydratingReplay(true);
    replayHydratingRef.current = true;
    const replayTimer = window.setTimeout(() => {
      replayHydratingRef.current = false;
      setIsHydratingReplay(false);
    }, 1400);
    const unsubscribe = subscribeAgentViewerEvents(
      activeLoopKind,
      activeRunId,
      (event) => {
        setConnected(true);
        const isReplay = replayHydratingRef.current;
        const normalizedEvent = normalizeLaneEvent(event);
        const phase = String(normalizedEvent?.payload?.phase || '');
        if (!firstEventLogged) {
          firstEventLogged = true;
          void postAgentViewerTimingLog(
            `first_event_received loop=${activeLoopKind} run=${activeRunId} elapsed_ms=${Date.now() - startedAtMs}`,
            {
              loop_kind: activeLoopKind,
              run_id: activeRunId,
              event_type: String(normalizedEvent?.event_type || 'status'),
              phase,
              replay: isReplay,
            },
          );
        }
        if (!isReplay && !firstLiveLogged) {
          firstLiveLogged = true;
          void postAgentViewerTimingLog(
            `first_live_event_received loop=${activeLoopKind} run=${activeRunId} elapsed_ms=${Date.now() - startedAtMs}`,
            {
              loop_kind: activeLoopKind,
              run_id: activeRunId,
              event_type: String(normalizedEvent?.event_type || 'status'),
              phase,
            },
          );
        }
        if (!firstPromptLogged && String(normalizedEvent?.event_type || '') === 'human_feedback_needed') {
          firstPromptLogged = true;
          void postAgentViewerTimingLog(
            `prompt_event_received loop=${activeLoopKind} run=${activeRunId} elapsed_ms=${Date.now() - startedAtMs}`,
            {
              loop_kind: activeLoopKind,
              run_id: activeRunId,
              event_type: 'human_feedback_needed',
              phase,
              replay: isReplay,
            },
          );
        }
        const taggedEvent = isReplay
          ? {
              ...normalizedEvent,
              payload: {
                ...(normalizedEvent.payload || {}),
                __replay: true,
              },
            }
          : normalizedEvent;
        setEvents((prev) => insertEventWithTickerReplacement(prev, taggedEvent));
      },
      () => setConnected(false),
      () => {
        setConnected(true);
        setConnectionEpoch((value) => value + 1);
      },
    );
    return () => {
      window.clearTimeout(replayTimer);
      replayHydratingRef.current = false;
      setIsHydratingReplay(false);
      unsubscribe();
    };
  }, [isOpen, activeLoopKind, activeRunId]);

  return {
    events,
    connected,
    connectionEpoch,
    isHydratingReplay,
  };
}

function normalizeLaneEvent(event: AgentViewerEvent): AgentViewerEvent {
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  const lane = String((event as AgentViewerEvent & { lane?: string }).lane || payload.lane || '').trim() || undefined;
  const laneSeqRaw = (event as AgentViewerEvent & { lane_seq?: number }).lane_seq ?? payload.lane_seq;
  const laneSeq = typeof laneSeqRaw === 'number' ? laneSeqRaw : undefined;
  const sessionId =
    String((event as AgentViewerEvent & { session_id?: string }).session_id || payload.session_id || '').trim() ||
    undefined;
  return {
    ...event,
    lane,
    lane_seq: laneSeq,
    session_id: sessionId,
    payload: payload as Record<string, unknown>,
  };
}

function insertEventWithTickerReplacement(prev: AgentViewerEvent[], event: AgentViewerEvent): AgentViewerEvent[] {
  const streamKind = String(event?.payload?.stream_kind || 'narration').toLowerCase();
  if (streamKind !== 'ticker') {
    return [event, ...prev].slice(0, 250);
  }
  const laneKey = String(event.lane || event.payload?.lane || 'unknown').toLowerCase();
  const filtered = prev.filter((existing) => {
    const existingKind = String(existing?.payload?.stream_kind || 'narration').toLowerCase();
    if (existingKind !== 'ticker') return true;
    const existingLane = String(existing.lane || existing.payload?.lane || 'unknown').toLowerCase();
    return existingLane !== laneKey;
  });
  return [event, ...filtered].slice(0, 250);
}
