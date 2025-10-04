// ============================================================================
// Dossier Selection Resolver - map DossierPath to renderable text
// ============================================================================
import { Dossier, DossierPath, Segment, Run, Draft } from '../../types/dossier';
import { dossierApi } from './dossierApi';
import { textApi } from '../textApi';
import { latestRunBestDraftPolicy } from './stitchingPolicy';
import { stitchToText } from './stitcher';

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
  // Prefer consensus drafts when available, otherwise fall back to "best" (or first available)
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

  const segment: Segment | null = ds.segments?.find(s => s.id === path.segmentId) ?? null;
  const run: Run | null = segment?.runs?.find(r => r.id === path.runId) ?? null;
  const drafts: Draft[] = (run?.drafts ?? []) as Draft[];
  let draft = drafts.find(d => d.id === path.draftId) ?? null;

  // If a specific version was requested (e.g., _v1/_v2 or _draft_{n}_v1/_v2),
  // map it to the base draft for context while still loading the requested version's content.
  if (!draft && path.draftId) {
    try {
      // Remove trailing _v1/_v2 only (do not touch _v{n} numbering)
      const baseCandidate = path.draftId.replace(/_v[12]$/, '');
      const maybe = drafts.find(d => d.id === baseCandidate) ?? null;
      if (maybe) {
        draft = maybe;
      }
    } catch {}
  }

  if (draft) {
    const dossierId = ds.id;
    const requestedDraftId = path.draftId || draft.id;
    const selectedIsConsensus = requestedDraftId.endsWith('_consensus_llm') || requestedDraftId.endsWith('_consensus_alignment');
    console.info(`selectionResolver: draft mode -> draftId=${requestedDraftId} dossierId=${dossierId} isConsensus=${selectedIsConsensus}`);
    let text = '';
    try {
      text = await textApi.getDraftText((run as any)?.transcriptionId || (run as any)?.transcription_id, requestedDraftId, dossierId);
    } catch (e) {
      console.warn('selectionResolver: failed to load requested draft text, returning empty', requestedDraftId, e);
    }
    return { mode: 'draft', path, text, context: { dossier: ds, segment, run, draft } };
  }

  // Handle run-level selection (no specific draft)
  if (run) {
    return await resolveRunText(ds, path);
  }

  // Handle segment-level selection (pick first run -> consensus or best)
  if (segment) {
    return await resolveSegmentText(ds, path);
  }

  console.info(`selectionResolver: dossier mode -> path=${JSON.stringify(path)}`);
  const text = await resolveDossierText(ds, path);
  return text;
}


