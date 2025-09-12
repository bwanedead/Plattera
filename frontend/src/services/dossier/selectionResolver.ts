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
    draft?.transcriptionId ||
    (draft as any)?.transcription_id ||
    run?.transcriptionId ||
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
  const text = await textApi.getDraftText(transcriptionId, draft.id);
  return { mode: 'draft', path, text, context: { dossier, segment, run, draft } };
}

async function resolveRunText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = findById(segment?.runs, path.runId);
  const draft = (run?.drafts || [])[0] || null;
  if (!segment || !run || !draft) {
    return { mode: 'run', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'run', path, text: '', context: { dossier, segment, run, draft } };
  }
  const text = await textApi.getDraftText(transcriptionId, draft.id);
  return { mode: 'run', path, text, context: { dossier, segment, run, draft } };
}

async function resolveSegmentText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = (segment?.runs || [])[0] || null;
  const draft = (run?.drafts || [])[0] || null;
  if (!segment || !run || !draft) {
    return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft } };
  }
  const text = await textApi.getDraftText(transcriptionId, draft.id);
  return { mode: 'segment', path, text, context: { dossier, segment, run, draft } };
}

async function resolveDossierText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const chosen = latestRunBestDraftPolicy(dossier);
  const text = await stitchToText(chosen, (tId, dId) => textApi.getDraftText(tId, dId));
  return { mode: 'dossier', path, text, context: { dossier } };
}

export async function resolveSelectionToText(path: DossierPath): Promise<ResolvedSelection> {
  if (!path?.dossierId) {
    return { mode: 'dossier', path, text: '' };
  }

  let dossier: Dossier | null = null;
  try {
    dossier = await dossierApi.getDossier(path.dossierId);
  } catch (e) {
    console.warn('resolveSelectionToText: failed to load dossier', e);
    // Fallback: load all and find
    try {
      const all = await dossierApi.getDossiers();
      dossier = (all || []).find((d) => d.id === path.dossierId) || null;
    } catch (e2) {
      console.warn('resolveSelectionToText: fallback getDossiers failed', e2);
    }
  }

  if (!dossier) {
    return { mode: 'dossier', path, text: '' };
  }

  // Priority by specificity
  if (path.draftId && path.runId && path.segmentId) {
    return resolveDraftText(dossier, path);
  }
  if (path.runId && path.segmentId) {
    return resolveRunText(dossier, path);
  }
  if (path.segmentId) {
    return resolveSegmentText(dossier, path);
  }
  return resolveDossierText(dossier, path);
}


