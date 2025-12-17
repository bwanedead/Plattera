import { useEffect, useState } from 'react';

interface BackendStatus {
  ready: boolean;
  checking: boolean;
  lastStartupMs?: number;
  estimateText?: string;
}

const STORAGE_KEY = 'plattera:lastBackendStartupMs';

/**
 * Tracks backend readiness by polling the /api/health endpoint.
 * 
 * - Stores the last startup time in localStorage to provide a rough estimate
 *   on subsequent launches.
 * - Continues polling until the backend reports healthy.
 */
export function useBackendReadiness(): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>({
    ready: false,
    checking: true,
  });

  useEffect(() => {
    let cancelled = false;
    const start = performance.now();

    let lastMs: number | undefined = undefined;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = parseInt(raw, 10);
        if (!Number.isNaN(parsed) && parsed > 0) {
          lastMs = parsed;
        }
      }
    } catch {
      lastMs = undefined;
    }

    const estimateText =
      lastMs && lastMs > 0
        ? `Backend usually starts in ~${Math.round(lastMs / 1000)}s`
        : 'Starting backend (typically 60–120s on first launch)…';

    setStatus(prev => ({
      ...prev,
      lastStartupMs: lastMs,
      estimateText,
    }));

    const poll = async () => {
      while (!cancelled) {
        try {
          const res = await fetch('http://127.0.0.1:8000/api/health', {
            cache: 'no-store',
          });
          if (res.ok) {
            const elapsed = performance.now() - start;
            try {
              localStorage.setItem(STORAGE_KEY, String(Math.round(elapsed)));
            } catch {
              // ignore storage errors
            }
            if (!cancelled) {
              setStatus({
                ready: true,
                checking: false,
                lastStartupMs: elapsed,
                estimateText: `Backend ready in ${Math.round(elapsed / 1000)}s`,
              });
            }
            return;
          }
        } catch {
          // ignore and retry
        }

        await new Promise(r => setTimeout(r, 1000));
      }
    };

    poll();

    return () => {
      cancelled = true;
    };
  }, []);

  return status;
}

