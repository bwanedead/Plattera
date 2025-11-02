export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEntry {
  ts: number;
  level: LogLevel;
  message: string;
  args?: any[];
  context?: string;
}

const STORAGE_KEY = 'plattera_logs';
const MAX_ENTRIES = 1000;

function readAll(): LogEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr : [];
  } catch {
    return [];
  }
}

function writeAll(entries: LogEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {}
}

export function add(level: LogLevel, message: string, args?: any[], context?: string): void {
  const entry: LogEntry = { ts: Date.now(), level, message, args, context };
  const arr = readAll();
  arr.push(entry);
  if (arr.length > MAX_ENTRIES) arr.splice(0, arr.length - MAX_ENTRIES);
  writeAll(arr);
}

export function clear(): void {
  try { localStorage.removeItem(STORAGE_KEY); } catch {}
}

export function toJson(pretty = true): string {
  const arr = readAll();
  return pretty ? JSON.stringify(arr, null, 2) : JSON.stringify(arr);
}

export function installGlobalLogCapture(): void {
  try {
    const orig = {
      log: console.log,
      info: console.info,
      warn: console.warn,
      error: console.error,
    } as const;

    // Capture only warnings and errors to reduce noise
    console.warn = (...args: any[]) => { try { add('warn', String(args?.[0] ?? ''), args); } catch {} orig.warn(...args); };
    console.error = (...args: any[]) => { try { add('error', String(args?.[0] ?? ''), args); } catch {} orig.error(...args); };

    window.addEventListener('error', (ev) => {
      try { add('error', (ev as ErrorEvent).message || 'Unhandled error', [(ev as any).error?.stack || String((ev as any).error || '')], 'window.onerror'); } catch {}
    });

    window.addEventListener('unhandledrejection', (ev: PromiseRejectionEvent) => {
      try { add('error', 'Unhandled promise rejection', [(ev as any).reason?.stack || String((ev as any).reason || '')], 'unhandledrejection'); } catch {}
    });

    // Minimal fetch logging (avoid bodies)
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
      const start = (window.performance && performance.now) ? performance.now() : Date.now();
      const method = (init?.method || 'GET').toUpperCase();
      const url = typeof input === 'string' ? input : (input as URL).toString?.() || String(input);
      try {
        const res = await originalFetch(input, init);
        const end = (window.performance && performance.now) ? performance.now() : Date.now();
        const ms = Math.round(end - start);
        // Only log non-OK responses to reduce clutter
        if (!res.ok) {
          try { add('warn', `HTTP ${method} ${url} -> ${res.status} (${ms}ms)`); } catch {}
        }
        return res;
      } catch (err: any) {
        const end = (window.performance && performance.now) ? performance.now() : Date.now();
        const ms = Math.round(end - start);
        try { add('error', `HTTP ${method} ${url} failed (${ms}ms)`, [String(err?.message || err)]); } catch {}
        throw err;
      }
    };
  } catch {}
}

export const logStore = { add, clear, toJson };


