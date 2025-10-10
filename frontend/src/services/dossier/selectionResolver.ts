// ============================================================================
// Dossier Selection Resolver - map DossierPath to renderable text
// ============================================================================
import { Dossier, DossierPath, Segment, Run, Draft } from '../../types/dossier';
import { dossierApi } from './dossierApi';
import { textApi } from '../textApi';
import { latestRunBestDraftPolicy } from './stitchingPolicy';
import { stitchToText } from './stitcher';
import { getVersionIndex } from './versioning';

type ResolveMode = 'draft' | 'run' | 'segment' | 'dossier';

export interface ResolvedSelection {
  mode: ResolveMode;
  path: DossierPath;
  text: string;
  context?: {
    dossier?: Dossier;
    segment?: Segment | null;
    run?: Run | null;
    draft?: Draft | null;
  };
}

function getTranscriptionIdSafe(run?: Run | null, draft?: Draft | null): string | undefined {
  return (
    (draft as any)?.transcriptionId ||
    (draft as any)?.transcription_id ||
    (run as any)?.transcriptionId ||
    (run as any)?.transcription_id
  );
}

function findById<T extends { id: string }>(list: T[] | undefined, id?: string): T | null {
  if (!list || !id) return null;
  return list.find((x) => x.id === id) || null;
}

async function resolveDraftText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = findById(segment?.runs, path.runId);
  const draft = findById(run?.drafts, path.draftId);
  if (!segment || !run || !draft) {
    return { mode: 'draft', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'draft', path, text: '', context: { dossier, segment, run, draft } };
  }
  let text = '';
  try {
    text = await textApi.getDraftText(transcriptionId, draft.id, dossier.id);
  } catch (e) {
    console.warn('selectionResolver: failed to load base draft text, returning empty', e);
  }
  return { mode: 'draft', path, text, context: { dossier, segment, run, draft } };
}

async function resolveRunText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = findById(segment?.runs, path.runId);
  
  // Prefer explicit final selection if present
  const finalId = (run as any)?.metadata?.final_selected_id as string | undefined;
  if (segment && run && typeof finalId === 'string' && finalId.trim()) {
    const transcriptionId = getTranscriptionIdSafe(run, null as any);
    if (transcriptionId) {
      try {
        const text = await textApi.getDraftText(transcriptionId, finalId, dossier.id);
        return { mode: 'run', path, text, context: { dossier, segment, run, draft: null } };
      } catch (e) {
        // Strict: no fallback on 404 for final selection
        console.warn(`selectionResolver: final selection ${finalId} failed to load, no fallback`, e);
        return { mode: 'run', path, text: '', context: { dossier, segment, run, draft: null } };
      }
    }
  }
  
  // Otherwise current policy (consensus/best/longest)
  let draft: Draft | null = null;
  const drafts = run?.drafts || [];
  if (drafts.length > 0) {
    // 1) Try consensus drafts (both LLM and alignment). If multiple, pick latest by createdAt.
    const consensusDrafts = drafts.filter((d: any) => typeof d.id === 'string' && (d.id.endsWith('_consensus_llm') || d.id.endsWith('_consensus_alignment')));
    if (consensusDrafts.length > 0) {
      draft = consensusDrafts
        .map((d: any) => ({ d, t: (() => { try { return d.metadata?.createdAt ? new Date(d.metadata.createdAt as any).getTime() : 0; } catch { return 0; } })() }))
        .sort((a, b) => b.t - a.t)[0].d;
    } else {
      // 2) Fall back to best flag
      draft = (drafts as any).find((d: any) => d.isBest || d.is_best) || null;
      // 3) Fall back to longest by size if best not flagged
      if (!draft) {
        draft = drafts
          .map((d: any) => ({ d, sz: Number(d.metadata?.sizeBytes || 0) }))
          .sort((a, b) => b.sz - a.sz)[0]?.d || drafts[0] || null;
      }
    }
  }
  if (!segment || !run || !draft) {
    return { mode: 'run', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'run', path, text: '', context: { dossier, segment, run, draft } };
  }
  let text = '';
  try {
    text = await textApi.getDraftText(transcriptionId, draft.id, dossier.id);
  } catch (e) {
    console.warn('selectionResolver: failed to load run draft text, returning empty', e);
  }
  return { mode: 'run', path, text, context: { dossier, segment, run, draft } };
}

async function resolveSegmentText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = (segment?.runs || [])[0] || null;
  
  // Prefer explicit final selection if present
  const finalId = (run as any)?.metadata?.final_selected_id as string | undefined;
  if (segment && run && typeof finalId === 'string' && finalId.trim()) {
    const transcriptionId = getTranscriptionIdSafe(run, null as any);
    if (transcriptionId) {
      try {
        const text = await textApi.getDraftText(transcriptionId, finalId, dossier.id);
        return { mode: 'segment', path, text, context: { dossier, segment, run, draft: null } };
      } catch (e) {
        // Strict: no fallback on 404 for final selection
        console.warn(`selectionResolver: final selection ${finalId} failed to load, no fallback`, e);
        return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft: null } };
      }
    }
  }
  
  // Prefer consensus drafts when available, otherwise fall back to "best" (or first available)
  let draft: Draft | null = null;
  const drafts = run?.drafts || [];
  if (drafts.length > 0) {
    const consensusDrafts = drafts.filter((d: any) => typeof d.id === 'string' && (d.id.endsWith('_consensus_llm') || d.id.endsWith('_consensus_alignment')));
    if (consensusDrafts.length > 0) {
      draft = consensusDrafts
        .map((d: any) => ({ d, t: (() => { try { return d.metadata?.createdAt ? new Date(d.metadata.createdAt as any).getTime() : 0; } catch { return 0; } })() }))
        .sort((a, b) => b.t - a.t)[0].d;
    } else {
      draft = (drafts as any).find((d: any) => d.isBest || d.is_best) || drafts[0] || null;
    }
  }
  if (!segment || !run || !draft) {
    return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft } };
  }
  let text = '';
  try {
    text = await textApi.getDraftText(transcriptionId, draft.id, dossier.id);
  } catch (e) {
    console.warn('selectionResolver: failed to load segment draft text, returning empty', e);
  }
  return { mode: 'segment', path, text, context: { dossier, segment, run, draft } };
}

async function resolveDossierText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const chosen = latestRunBestDraftPolicy(dossier);
  const text = await stitchToText(chosen, (tId, dId) => textApi.getDraftText(tId, dId));
  return { mode: 'dossier', path, text, context: { dossier } };
}

export async function resolveSelectionToText(path: DossierPath, dossier?: Dossier): Promise<ResolvedSelection> {
  let ds: Dossier | undefined = dossier;
  if (!ds && path.dossierId) {
    ds = await dossierApi.getDossier(path.dossierId);
  }
  if (!ds) {
    return { mode: 'dossier', path, text: '', context: { dossier: ds } };
  }

  // Compute a deterministic fetch plan: exact versionedId + transcriptionId
  const segment: Segment | null = ds.segments?.find(s => s.id === path.segmentId) ?? null;
  const run: Run | null = segment?.runs?.find(r => r.id === path.runId) ?? null;

  // Exact versioned selection via index
  if (path.draftId) {
    try {
      const index = getVersionIndex(ds);
      const entry = index.get(path.draftId);
      if (entry) {
        const draftCtx = (run?.drafts || []).find(d => d.id === entry.baseDraftId) || null;
        let text = '';
        try {
          text = await textApi.getDraftText(entry.transcriptionId, entry.versionedId, ds.id);
        } catch (e) {
          console.warn('selectionResolver: failed to load text for', entry.versionedId, e);
        }
        return { mode: 'draft', path, text, context: { dossier: ds, segment, run, draft: draftCtx } };
      }
    } catch {}

    // No index match: still allow direct fetch using run transcriptionId (no fallback to best)
    if (run) {
      const tId = (run as any)?.transcriptionId || (run as any)?.transcription_id;
      if (tId) {
        let text = '';
        try {
          text = await textApi.getDraftText(tId, path.draftId, ds.id);
        } catch (e) {
          console.warn('selectionResolver: direct versioned fetch failed', path.draftId, e);
        }
        return { mode: 'draft', path, text, context: { dossier: ds, segment, run, draft: null } };
      }
    }
  }

  // No explicit draftId: use existing policy, but resolve to concrete HEAD version
  if (run) {
    const drafts: Draft[] = (run?.drafts ?? []) as Draft[];
    let chosen: Draft | null = null;
    const consensus = drafts.filter((d: any) => (d.id || '').endsWith('_consensus_llm') || (d.id || '').endsWith('_consensus_alignment'));
    if (consensus.length > 0) {
      chosen = consensus
        .map((d: any) => ({ d, t: (() => { try { return d.metadata?.createdAt ? new Date(d.metadata.createdAt as any).getTime() : 0; } catch { return 0; } })() }))
        .sort((a, b) => b.t - a.t)[0].d;
    } else {
      chosen = (drafts as any).find((d: any) => d.isBest || d.is_best) || drafts[0] || null;
    }
    if (!chosen) {
      return { mode: 'run', path, text: '', context: { dossier: ds, segment, run, draft: null } };
    }

    const tId = (run as any)?.transcriptionId || (run as any)?.transcription_id || '';
    const head =
      ((chosen.metadata as any)?.versions?.raw?.head) ||
      ((chosen.metadata as any)?.versions?.alignment?.head) ||
      ((chosen.metadata as any)?.versions?.consensus?.llm?.head) ||
      ((chosen.metadata as any)?.versions?.consensus?.alignment?.head) ||
      'v1';
    const pos = (chosen.position ?? 0) + 1;
    const baseTid = String(tId).replace(/_v[12]$/, '');

    let versionedId = '';
    if (/_consensus_llm$/.test(String(chosen.id))) {
      versionedId = `${baseTid}_consensus_llm_${head}`;
    } else if (/_consensus_alignment$/.test(String(chosen.id))) {
      versionedId = `${baseTid}_consensus_alignment_${head}`;
    } else {
      const hasRaw = (chosen.metadata as any)?.versions?.raw?.head === head;
      if (hasRaw) {
        versionedId = `${baseTid}_v${pos}_${head}`;
      } else {
        versionedId = `${baseTid}_draft_${pos}_${head}`;
      }
    }

    let text = '';
    try {
      text = await textApi.getDraftText(tId, versionedId, ds.id);
    } catch (e) {
      console.warn('selectionResolver: failed to load run HEAD text', versionedId, e);
    }
    return { mode: 'draft', path, text, context: { dossier: ds, segment, run, draft: chosen } };
  }

  // Handle segment-level selection (pick first run -> consensus or best)
  if (segment) {
    return await resolveSegmentText(ds, path);
  }

  console.info(`selectionResolver: dossier mode -> path=${JSON.stringify(path)}`);
  const text = await resolveDossierText(ds, path);
  return text;
}


