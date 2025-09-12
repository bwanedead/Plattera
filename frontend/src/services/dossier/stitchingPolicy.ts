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
    const best = (run.drafts || []).find(d => d.isBest) || run.drafts?.[0];
    if (!best) continue;
    chosen.push({
      segmentId: segment.id,
      transcriptionId: best.transcriptionId,
      draftId: best.id
    });
  }
  return chosen;
};


