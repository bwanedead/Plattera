import React from 'react';
import { subscribeAgentViewerEvents, type AgentViewerEvent, type AgentViewerLoopKind } from '../../../services/agentViewerApi';

type Params = {
  isOpen: boolean;
  activeLoopKind: AgentViewerLoopKind | null;
  activeRunId: string | null;
};

export function useAgentViewerStream({ isOpen, activeLoopKind, activeRunId }: Params) {
  const [events, setEvents] = React.useState<AgentViewerEvent[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [isHydratingReplay, setIsHydratingReplay] = React.useState(false);
  const replayHydratingRef = React.useRef(false);

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) return;
    const startedAtMs = Date.now();
    let firstEventLogged = false;
    let firstLiveLogged = false;
    let firstPromptLogged = false;
    void postFrontendTimingLog(
      `subscribe_start loop=${activeLoopKind} run=${activeRunId}`,
      { loop_kind: activeLoopKind, run_id: activeRunId },
    );
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
          void postFrontendTimingLog(
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
          void postFrontendTimingLog(
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
          void postFrontendTimingLog(
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
        const taggedEvent =
          isReplay
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
    );
    return () => {
      window.clearTimeout(replayTimer);
      replayHydratingRef.current = false;
      setIsHydratingReplay(false);
      unsubscribe();
    };
  }, [isOpen, activeLoopKind, activeRunId]);

  React.useEffect(() => {
    if (!isOpen) return;
    const endpoint = 'http://127.0.0.1:8000/api/logs/frontend';
    const postLog = (level: string, args: any[]) => {
      try {
        const text = args
          .map((v) => {
            if (typeof v === 'string') return v;
            try {
              return JSON.stringify(v);
            } catch {
              return String(v);
            }
          })
          .join(' ');
        void fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            level,
            message: text.slice(0, 3800),
            source: 'agent_viewer_client',
            ts: Date.now() / 1000,
          }),
        }).catch(() => {
          // Non-fatal: backend log sink may be temporarily unavailable.
        });
      } catch {
        // ignore
      }
    };

    const originalWarn = console.warn;
    const originalError = console.error;
    console.warn = (...args: any[]) => {
      postLog('WARNING', args);
      originalWarn(...args);
    };
    console.error = (...args: any[]) => {
      postLog('ERROR', args);
      originalError(...args);
    };

    const onWindowError = (evt: ErrorEvent) => {
      postLog('ERROR', [evt.message, evt.filename, evt.lineno, evt.colno]);
    };
    window.addEventListener('error', onWindowError);

    return () => {
      console.warn = originalWarn;
      console.error = originalError;
      window.removeEventListener('error', onWindowError);
    };
  }, [isOpen]);

  return {
    events,
    setEvents,
    connected,
    setConnected,
    isHydratingReplay,
  };
}

function normalizeLaneEvent(event: AgentViewerEvent): AgentViewerEvent {
  const payload = event.payload && typeof event.payload === 'object' ? event.payload : {};
  const lane = String((event as any).lane || payload.lane || '').trim() || undefined;
  const laneSeqRaw = (event as any).lane_seq ?? payload.lane_seq;
  const laneSeq = typeof laneSeqRaw === 'number' ? laneSeqRaw : undefined;
  const sessionId = String((event as any).session_id || payload.session_id || '').trim() || undefined;
  return {
    ...event,
    lane,
    lane_seq: laneSeq,
    session_id: sessionId,
    payload: payload as Record<string, any>,
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

async function postFrontendTimingLog(message: string, metadata?: Record<string, any>): Promise<void> {
  try {
    await fetch('http://127.0.0.1:8000/api/logs/frontend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level: 'INFO',
        source: 'agent_viewer_timing',
        message: `AGENT_VIEWER_TIMING ► ${message}`,
        ts: Date.now() / 1000,
        meta: metadata || {},
      }),
    });
  } catch {
    // ignore timing log failures
  }
}
