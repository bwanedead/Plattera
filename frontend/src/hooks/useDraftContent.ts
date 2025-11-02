// ============================================================================
// useDraftContent - fetches and caches draft text by (transcriptionId, draftId)
// ============================================================================

import { useEffect, useMemo, useRef, useState } from 'react';
import { textApi } from '../services/textApi';

type DraftRef = { transcriptionId: string; draftId: string } | null | undefined;

const cache = new Map<string, string>();

function getCacheKey(ref: { transcriptionId: string; draftId: string }) {
  return `${ref.transcriptionId}::${ref.draftId}`;
}

export function useDraftContent(ref: DraftRef) {
  const [text, setText] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const key = useMemo(() => {
    if (!ref) return null;
    return getCacheKey(ref);
  }, [ref?.transcriptionId, ref?.draftId]);

  const mounted = useRef(true);
  useEffect(() => () => { mounted.current = false; }, []);

  useEffect(() => {
    if (!ref || !key) {
      setText('');
      setError(null);
      setIsLoading(false);
      return;
    }

    // Serve from cache if present
    if (cache.has(key)) {
      setText(cache.get(key) || '');
      setIsLoading(false);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    textApi
      .getDraftText(ref.transcriptionId, ref.draftId)
      .then((t) => {
        cache.set(key, t || '');
        if (mounted.current) {
          setText(t || '');
          setIsLoading(false);
        }
      })
      .catch((e) => {
        if (mounted.current) {
          setError(e?.message || 'Failed to load draft text');
          setIsLoading(false);
        }
      });
  }, [key, ref?.transcriptionId, ref?.draftId]);

  return { text, isLoading, error };
}


