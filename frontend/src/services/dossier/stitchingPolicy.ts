// ============================================================================
// Stitching Policy - choose drafts to stitch across segments
// ============================================================================
import { Dossier, Run } from '../../types/dossier';

export interface ChosenDraftRef {
  segmentId: string;
  transcriptionId: string;
  draftId: string;
}

export type StitchPolicy = (dossier: Dossier) => ChosenDraftRef[];

function pickLatestRun(runs: Run[]): Run | null {
  if (!runs || runs.length === 0) return null;
  // Prefer metadata.createdAt, else position
  const withDate = runs
    .map(r => ({
      run: r,
      t: (() => {
        try { return r.metadata?.createdAt ? new Date(r.metadata.createdAt as any).getTime() : 0; } catch { return 0; }
      })()
    }))
    .sort((a, b) => b.t - a.t);
  const candidate = withDate[0]?.run || runs.sort((a, b) => b.position - a.position)[0];
  return candidate || null;
}

export const latestRunBestDraftPolicy: StitchPolicy = (dossier) => {
  const chosen: ChosenDraftRef[] = [];
  for (const segment of dossier.segments || []) {
    const run = pickLatestRun(segment.runs || []);
    if (!run) continue;
    const drafts = run.drafts || [];
    // Prefer consensus drafts first (LLM or alignment); if multiple, pick latest by createdAt
    let pick: any = null;
    const consensusDrafts = drafts.filter((d: any) => typeof d.id === 'string' && (d.id.endsWith('_consensus_llm') || d.id.endsWith('_consensus_alignment')));
    if (consensusDrafts.length > 0) {
      pick = consensusDrafts
        .map((d: any) => ({ d, t: (() => { try { return d.metadata?.createdAt ? new Date(d.metadata.createdAt as any).getTime() : 0; } catch { return 0; } })() }))
        .sort((a, b) => b.t - a.t)[0].d;
    } else {
      // Fall back to best, then longest, then first
      pick = (drafts as any).find((d: any) => d.isBest || d.is_best) || null;
      if (!pick) {
        pick = drafts
          .map((d: any) => ({ d, sz: Number(d.metadata?.sizeBytes || 0) }))
          .sort((a, b) => b.sz - a.sz)[0]?.d || drafts[0] || null;
      }
    }
    if (!pick) continue;
    chosen.push({
      segmentId: segment.id,
      transcriptionId: (pick as any).transcriptionId || (pick as any).transcription_id,
      draftId: pick.id
    });
  }
  return chosen;
};


