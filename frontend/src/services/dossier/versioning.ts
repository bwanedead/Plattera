// ============================================================================
// Dossier Versioning Utilities
// - Parse/build versioned IDs
// - Build fast index of versionedId -> { transcriptionId, baseDraftId, context }
// - Lightweight cache + invalidation
// ============================================================================

export type VersionKind = 'raw' | 'align' | 'cons_llm' | 'cons_align';
export type VersionHead = 'v1' | 'v2';

export interface DraftVersionKey {
  transcriptionId: string;
  kind: VersionKind;
  rawIndex?: number; // 1-based for raw/align
  head: VersionHead;
  versionedId: string; // canonical id to fetch/display
}

export function parseVersionedId(id: string): { kind: VersionKind; rawIndex?: number; head?: VersionHead } | null {
  try {
    if (/_v\d+_v(1|2)$/.test(id)) {
      // raw: <tid>_v{n}_v1|v2
      const m = id.match(/_v(\d+)_v(1|2)$/);
      if (!m) return null;
      return { kind: 'raw', rawIndex: parseInt(m[1], 10), head: (`v${m[2]}` as VersionHead) };
    }
    if (/_draft_\d+_v(1|2)$/.test(id)) {
      // align: <tid>_draft_{n}_v1|v2
      const m = id.match(/_draft_(\d+)_v(1|2)$/);
      if (!m) return null;
      return { kind: 'align', rawIndex: parseInt(m[1], 10), head: (`v${m[2]}` as VersionHead) };
    }
    if (/(_consensus_llm|_consensus_alignment)(_v(1|2))?$/.test(id)) {
      if (/_consensus_llm/.test(id)) {
        const hv = id.match(/_v(1|2)$/)?.[1];
        return { kind: 'cons_llm', head: (hv ? (`v${hv}` as VersionHead) : undefined) };
      } else {
        const hv = id.match(/_v(1|2)$/)?.[1];
        return { kind: 'cons_align', head: (hv ? (`v${hv}` as VersionHead) : undefined) };
      }
    }
  } catch {}
  return null;
}

export function buildVersionedId(tid: string, key: { kind: VersionKind; rawIndex?: number; head: VersionHead }): string {
  if (key.kind === 'raw') return `${tid}_v${key.rawIndex}_v${key.head === 'v1' ? '1' : '2'}`;
  if (key.kind === 'align') return `${tid}_draft_${key.rawIndex}_v${key.head === 'v1' ? '1' : '2'}`;
  if (key.kind === 'cons_llm') return `${tid}_consensus_llm_${key.head}`;
  if (key.kind === 'cons_align') return `${tid}_consensus_alignment_${key.head}`;
  return tid;
}

export interface VersionIndexEntry {
  versionedId: string;
  transcriptionId: string;
  baseDraftId?: string; // e.g., <tid>_v{n} for raw/align
  context: { runId: string; segmentId: string; dossierId: string };
}

// Cache of dossierId -> Map<versionedId, VersionIndexEntry>
const INDEX_CACHE = new Map<string, Map<string, VersionIndexEntry>>();

export function invalidateVersionIndex(dossierId?: string) {
  if (!dossierId) {
    INDEX_CACHE.clear();
    return;
  }
  INDEX_CACHE.delete(dossierId);
}

export function getVersionIndex(dossier: any): Map<string, VersionIndexEntry> {
  const dossierId = String(dossier?.id || '');
  if (!dossierId) return new Map();
  const cached = INDEX_CACHE.get(dossierId);
  if (cached) return cached;
  const idx = buildVersionIndex(dossier);
  INDEX_CACHE.set(dossierId, idx);
  return idx;
}

export function buildVersionIndex(dossier: any): Map<string, VersionIndexEntry> {
  const map = new Map<string, VersionIndexEntry>();
  const dossierId = dossier.id;
  for (const seg of (dossier.segments || [])) {
    for (const run of (seg.runs || [])) {
      const tIdRaw = (run as any).transcription_id || (run as any).transcriptionId;
      if (!tIdRaw) continue;
      const tId = String(tIdRaw);
      const drafts = run.drafts || [];
      for (const dr of drafts) {
        const pos = (dr.position ?? 0) + 1;
        const baseTid = tId.replace(/_v[12]$/, '');
        const baseRaw = `${baseTid}_v${pos}`;
        const versions = (dr.metadata as any)?.versions || {};

        // raw v1/v2
        if (versions.raw?.v1) {
          const vid = `${baseRaw}_v1`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: baseRaw, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }
        if (versions.raw?.v2) {
          const vid = `${baseRaw}_v2`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: baseRaw, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }

        // align Av1/Av2
        if (versions.alignment?.v1) {
          const vid = `${baseTid}_draft_${pos}_v1`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: baseRaw, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }
        if (versions.alignment?.v2) {
          const vid = `${baseTid}_draft_${pos}_v2`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: baseRaw, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }

        // consensus llm
        if (versions.consensus?.llm?.v1) {
          const vid = `${baseTid}_consensus_llm_v1`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: dr.id, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }
        if (versions.consensus?.llm?.v2) {
          const vid = `${baseTid}_consensus_llm_v2`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: dr.id, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }

        // consensus alignment
        if (versions.consensus?.alignment?.v1) {
          const vid = `${baseTid}_consensus_alignment_v1`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: dr.id, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }
        if (versions.consensus?.alignment?.v2) {
          const vid = `${baseTid}_consensus_alignment_v2`;
          map.set(vid, { versionedId: vid, transcriptionId: tId, baseDraftId: dr.id, context: { runId: run.id, segmentId: seg.id, dossierId } });
        }
      }
    }
  }
  return map;
}

// Browser-only: invalidate cached indexes on global refresh events
if (typeof document !== 'undefined') {
  const tryAdd = (name: string) => {
    try {
      document.addEventListener(name, (ev: Event) => {
        try {
          const detail = (ev as CustomEvent)?.detail || {};
          const dossierId = detail?.dossierId || detail?.dossier_id;
          invalidateVersionIndex(dossierId);
        } catch {
          invalidateVersionIndex();
        }
      });
    } catch {}
  };
  tryAdd('dossiers:refresh');
  tryAdd('dossier:refreshOne');
  tryAdd('draft:saved');
  tryAdd('draft:reverted');
}


