import { useEffect } from 'react';
import { Dossier } from '../types/dossier';

/**
 * Lightweight polling hook that refreshes dossiers while any run/draft is in processing state.
 * Keeps polling logic separate from state management for clarity and scalability.
 */
export function useProcessingPoller(
  dossiers: Dossier[] | undefined,
  refresh: () => void,
  intervalMs: number = 2000,
  active: boolean = false
) {
  useEffect(() => {
    if (!active) return;
    if (!Array.isArray(dossiers) || dossiers.length === 0) return;

    // Determine if any item is still processing
    const hasProcessing = dossiers.some(dossier =>
      (dossier.segments || []).some(segment =>
        (segment.runs || []).some(run =>
          run?.metadata?.status === 'processing' ||
          (run.drafts || []).some(draft => draft?.metadata?.status === 'processing')
        )
      )
    );

    if (!hasProcessing) return;

    const id = setInterval(() => {
      try { refresh(); } catch {}
    }, intervalMs);

    return () => clearInterval(id);
  }, [active, dossiers, refresh, intervalMs]);
}


