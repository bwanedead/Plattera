const API_BASE =
  (typeof process !== 'undefined' &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE as string)) ||
  'http://127.0.0.1:8000';

const FRONTEND_LOG_ENDPOINT = `${API_BASE}/api/logs/frontend`;

export async function postAgentViewerFrontendLog(payload: {
  level: string;
  message: string;
  source: string;
  ts?: number;
  meta?: Record<string, unknown>;
}): Promise<void> {
  try {
    await fetch(FRONTEND_LOG_ENDPOINT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...payload,
        ts: payload.ts ?? Date.now() / 1000,
      }),
    });
  } catch {
    // Non-fatal: backend log sink may be temporarily unavailable.
  }
}

export async function postAgentViewerTimingLog(
  message: string,
  metadata?: Record<string, unknown>,
): Promise<void> {
  await postAgentViewerFrontendLog({
    level: 'INFO',
    source: 'agent_viewer_timing',
    message: `AGENT_VIEWER_TIMING ► ${message}`,
    meta: metadata,
  });
}

export function installAgentViewerClientLogBridge(): () => void {
  const postLog = (level: string, args: unknown[]) => {
    try {
      const text = args
        .map((value) => {
          if (typeof value === 'string') return value;
          try {
            return JSON.stringify(value);
          } catch {
            return String(value);
          }
        })
        .join(' ');
      void postAgentViewerFrontendLog({
        level,
        message: text.slice(0, 3800),
        source: 'agent_viewer_client',
      });
    } catch {
      // ignore
    }
  };

  const originalWarn = console.warn;
  const originalError = console.error;
  console.warn = (...args: unknown[]) => {
    postLog('WARNING', args);
    originalWarn(...args);
  };
  console.error = (...args: unknown[]) => {
    postLog('ERROR', args);
    originalError(...args);
  };

  const onWindowError = (event: ErrorEvent) => {
    postLog('ERROR', [event.message, event.filename, event.lineno, event.colno]);
  };
  window.addEventListener('error', onWindowError);

  return () => {
    console.warn = originalWarn;
    console.error = originalError;
    window.removeEventListener('error', onWindowError);
  };
}
