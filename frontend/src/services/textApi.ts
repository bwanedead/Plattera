// ============================================================================
// TEXT API CLIENT - FETCH DRAFT CONTENT BY ID
// ============================================================================

const BASE_URL = 'http://localhost:8000/api';

// Simple in-memory caches with TTL and in-flight request de-duplication
type CacheEntry<T> = { value: T; expiresAt: number };
const JSON_CACHE = new Map<string, CacheEntry<any>>();
const TEXT_CACHE = new Map<string, CacheEntry<string>>();
const IN_FLIGHT = new Map<string, Promise<any>>();
const DEFAULT_TTL_MS = 5 * 60 * 1000; // 5 minutes

function cacheKeyJson(draftId: string, dossierId?: string) {
  return `json:${draftId}:${dossierId || ''}`;
}

function cacheKeyText(draftId: string, dossierId?: string) {
  return `text:${draftId}:${dossierId || ''}`;
}

function now() { return Date.now(); }

function getFromCache<T>(map: Map<string, CacheEntry<T>>, key: string): T | undefined {
  const entry = map.get(key);
  if (!entry) return undefined;
  if (entry.expiresAt < now()) {
    map.delete(key);
    return undefined;
  }
  return entry.value;
}

function setInCache<T>(map: Map<string, CacheEntry<T>>, key: string, value: T, ttlMs: number = DEFAULT_TTL_MS) {
  map.set(key, { value, expiresAt: now() + ttlMs });
}

function invalidateCachesForDraft(draftId?: string, dossierId?: string) {
  if (!draftId) {
    JSON_CACHE.clear();
    TEXT_CACHE.clear();
    return;
  }
  const jsonKey = cacheKeyJson(draftId, dossierId);
  const textKey = cacheKeyText(draftId, dossierId);
  JSON_CACHE.delete(jsonKey);
  TEXT_CACHE.delete(textKey);
}

// Listen for global events to invalidate caches on edits/reverts/refresh
if (typeof document !== 'undefined') {
  const safeAdd = (name: string) => {
    try {
      document.addEventListener(name, (ev: Event) => {
        const detail = (ev as CustomEvent)?.detail || {};
        invalidateCachesForDraft(detail?.draftId, detail?.dossierId);
      });
    } catch {}
  };
  safeAdd('draft:saved');
  safeAdd('draft:reverted');
  safeAdd('dossiers:refresh');
}

export class TextApiError extends Error {
  constructor(message: string, public statusCode?: number, public details?: any) {
    super(message);
    this.name = 'TextApiError';
  }
}

export const textApi = {
  async getDraftText(transcriptionId: string, draftId: string, dossierId?: string): Promise<string> {
    const key = cacheKeyText(draftId, dossierId);
    const cached = getFromCache<string>(TEXT_CACHE, key);
    if (cached !== undefined) return cached;

    const json = await this.getDraftJson(transcriptionId, draftId, dossierId);
    try {
      // Treat both base and versioned consensus ids the same (_consensus_llm[_v1|_v2], _consensus_alignment[_v1|_v2])
      const isConsensusId = draftId.includes('_consensus_llm') || draftId.includes('_consensus_alignment');
      if (isConsensusId && json && typeof json === 'object') {
        if ('text' in (json as any)) {
          const value = String((json as any).text || '');
          setInCache(TEXT_CACHE, key, value);
          return value;
        }
        // If consensus JSON happens to be saved as sections, fall through to sections handling below
      }
      // Common JSON schema path
      if (json && typeof json === 'object') {
        const maybeSections = (json as any).sections;
        if (Array.isArray(maybeSections)) {
          const text = maybeSections.map((s: any) => s?.body ?? '').join('\n\n').trim();
          setInCache(TEXT_CACHE, key, text);
          return text;
        }
      }
      const value = typeof json === 'string' ? json : JSON.stringify(json);
      setInCache(TEXT_CACHE, key, value);
      return value;
    } catch (e) {
      throw new TextApiError('Failed to parse draft text', undefined, e);
    }
  },

  async getDraftJson(transcriptionId: string, draftId: string, dossierId?: string): Promise<any> {
    const primary = `${BASE_URL}/dossier-management/drafts/${encodeURIComponent(draftId)}${dossierId ? `?dossier_id=${encodeURIComponent(dossierId)}` : ''}`;
    const key = cacheKeyJson(draftId, dossierId);
    const cached = getFromCache<any>(JSON_CACHE, key);
    if (cached !== undefined) return cached;

    // In-flight de-duplication
    if (IN_FLIGHT.has(primary)) {
      try {
        const val = await IN_FLIGHT.get(primary)!;
        setInCache(JSON_CACHE, key, val);
        return val;
      } finally {
        IN_FLIGHT.delete(primary);
      }
    }

    const p = (async () => {
      const res = await fetch(primary);
      const data = await res.json().catch(() => null);
      if (!res.ok) {
        throw new TextApiError(`HTTP ${res.status} loading draft`, res.status, data);
      }
      const payload = (data?.data ?? data);
      setInCache(JSON_CACHE, key, payload);
      // Also invalidate derived text cache for this draft (it will be recomputed)
      TEXT_CACHE.delete(cacheKeyText(draftId, dossierId));
      return payload;
    })();

    IN_FLIGHT.set(primary, p);
    try {
      return await p;
    } finally {
      IN_FLIGHT.delete(primary);
    }
  }
};


