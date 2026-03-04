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
        const taggedEvent =
          replayHydratingRef.current
            ? {
                ...event,
                payload: {
                  ...(event.payload || {}),
                  __replay: true,
                },
              }
            : event;
        setEvents((prev) => [taggedEvent, ...prev].slice(0, 250));
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
