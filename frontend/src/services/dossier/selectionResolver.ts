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
  const text = await textApi.getDraftText(transcriptionId, draft.id, dossier.id);
  return { mode: 'draft', path, text, context: { dossier, segment, run, draft } };
}

async function resolveRunText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = findById(segment?.runs, path.runId);
  const draft = ((run?.drafts || []).find(d => (d as any).isBest || (d as any).is_best) || (run?.drafts || [])[0]) || null;
  if (!segment || !run || !draft) {
    return { mode: 'run', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'run', path, text: '', context: { dossier, segment, run, draft } };
  }
  const text = await textApi.getDraftText(transcriptionId, draft.id, dossier.id);
  return { mode: 'run', path, text, context: { dossier, segment, run, draft } };
}

async function resolveSegmentText(dossier: Dossier, path: DossierPath): Promise<ResolvedSelection> {
  const segment = findById(dossier.segments, path.segmentId);
  const run = (segment?.runs || [])[0] || null;
  const draft = ((run?.drafts || []).find(d => (d as any).isBest || (d as any).is_best) || (run?.drafts || [])[0]) || null;
  if (!segment || !run || !draft) {
    return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft } };
  }
  const transcriptionId = getTranscriptionIdSafe(run, draft);
  if (!transcriptionId) {
    return { mode: 'segment', path, text: '', context: { dossier, segment, run, draft } };
  }
  const text = await textApi.getDraftText(transcriptionId, draft.id, dossier.id);
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
  const draft = drafts.find(d => d.id === path.draftId) ?? null;

  if (draft) {
    const draftId = draft.id;
    const dossierId = ds.id;
    const selectedIsConsensus = draftId.endsWith('_consensus_llm') || draftId.endsWith('_consensus_alignment');
    console.info(`selectionResolver: draft mode -> draftId=${draftId} dossierId=${dossierId} isConsensus=${selectedIsConsensus}`);
    const text = await textApi.getDraftText((run as any)?.transcriptionId || (run as any)?.transcription_id, draftId, dossierId);
    return { mode: 'draft', path, text, context: { dossier: ds, segment, run, draft } };
  }

  console.info(`selectionResolver: non-draft mode -> path=${JSON.stringify(path)}`);
  const text = stitchToText(await latestRunBestDraftPolicy(ds));
  return { mode: 'dossier', path, text, context: { dossier: ds, segment, run, draft: null } };
}


