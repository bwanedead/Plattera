// ============================================================================
// Stitching Policy - choose drafts to stitch across segments
// ============================================================================
import { Dossier, Run } from '../../types/dossier';
import { pickStrictVersionedId, pickConsensusStrictId, pickRunFinalId } from './versionResolver';

export interface ChosenDraftRef {
  segmentId: string;
  transcriptionId: string;
  draftId: string;
}

export type StitchPolicy = (dossier: Dossier) => ChosenDraftRef[];

function pickFirstRun(runs: Run[]): Run | null {
  if (!runs || runs.length === 0) return null;
  const sorted = [...runs].sort((a: any, b: any) => (a.position ?? 0) - (b.position ?? 0));
  return sorted[0] || null;
}

export const latestRunBestDraftPolicy: StitchPolicy = (dossier) => {
  const chosen: ChosenDraftRef[] = [];
  for (const segment of dossier.segments || []) {
    const run = pickFirstRun(segment.runs || []);
    if (!run) continue;
    
    // Finals-first
    const finalId = pickRunFinalId(run as any);
    if (finalId) {
      chosen.push({
        segmentId: segment.id,
        transcriptionId: (run as any).transcriptionId || (run as any).transcription_id,
        draftId: finalId
      });
      continue;
    }
    
    const drafts = run.drafts || [];
    // Prefer consensus drafts first (LLM or alignment); if multiple, pick latest by createdAt
    const llmId = pickConsensusStrictId(run as any, 'llm');
    if (llmId) {
      chosen.push({
        segmentId: segment.id,
        transcriptionId: (run as any).transcriptionId || (run as any).transcription_id,
        draftId: llmId
      });
      continue;
    }
    const alignId = pickConsensusStrictId(run as any, 'alignment');
    if (alignId) {
      chosen.push({
        segmentId: segment.id,
        transcriptionId: (run as any).transcriptionId || (run as any).transcription_id,
        draftId: alignId
      });
      continue;
    }

    // Fall back to best, then longest, then first; then convert to strict id
    let pick: any = (drafts as any).find((d: any) => d.isBest || d.is_best) || null;
    if (!pick) {
      pick = drafts
        .map((d: any) => ({ d, sz: Number(d.metadata?.sizeBytes || 0) }))
        .sort((a, b) => b.sz - a.sz)[0]?.d || drafts[0] || null;
    }
    if (!pick) continue;
    const strictId = pickStrictVersionedId(run as any, pick as any);
    chosen.push({
      segmentId: segment.id,
      transcriptionId: (run as any).transcriptionId || (run as any).transcription_id,
      draftId: strictId
    });
  }
  return chosen;
};


