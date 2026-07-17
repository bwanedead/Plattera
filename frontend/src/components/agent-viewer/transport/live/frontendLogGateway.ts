import {
  acquireClientLogBridgeRef,
  getClientLogBridgeRefCount,
  releaseClientLogBridgeRef,
} from './clientLogBridgeRefCount';

const API_BASE =
  (typeof process !== 'undefined' &&
    process.env &&
    (process.env.NEXT_PUBLIC_API_BASE as string)) ||
  'http://127.0.0.1:8000';

const FRONTEND_LOG_ENDPOINT = `${API_BASE}/api/logs/frontend`;

let bridgeTeardown: (() => void) | null = null;
let originalWarn: typeof console.warn | null = null;
let originalError: typeof console.error | null = null;

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

function installBridge(): () => void {
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

  originalWarn = console.warn;
  originalError = console.error;
  console.warn = (...args: unknown[]) => {
    postLog('WARNING', args);
    originalWarn?.(...args);
  };
  console.error = (...args: unknown[]) => {
    postLog('ERROR', args);
    originalError?.(...args);
  };

  const onWindowError = (event: ErrorEvent) => {
    postLog('ERROR', [event.message, event.filename, event.lineno, event.colno]);
  };
  window.addEventListener('error', onWindowError);

  return () => {
    if (originalWarn) console.warn = originalWarn;
    if (originalError) console.error = originalError;
    window.removeEventListener('error', onWindowError);
    originalWarn = null;
    originalError = null;
  };
}

export function acquireAgentViewerClientLogBridge(): () => void {
  acquireClientLogBridgeRef();
  if (typeof window !== 'undefined' && getClientLogBridgeRefCount() === 1) {
    bridgeTeardown = installBridge();
  }
  let released = false;
  return () => {
    if (released) return;
    released = true;
    releaseClientLogBridgeRef();
    if (typeof window !== 'undefined' && getClientLogBridgeRefCount() === 0 && bridgeTeardown) {
      bridgeTeardown();
      bridgeTeardown = null;
    }
  };
}

/** @deprecated Use acquireAgentViewerClientLogBridge for ref-counted installs. */
export function installAgentViewerClientLogBridge(): () => void {
  return acquireAgentViewerClientLogBridge();
}

export function getAgentViewerClientLogBridgeRefCount(): number {
  return getClientLogBridgeRefCount();
}
