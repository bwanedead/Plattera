// ============================================================================
// Stitcher - builds stitched text from chosen draft refs
// ============================================================================
import { Dossier } from '../../types/dossier';
import { ChosenDraftRef, StitchPolicy } from './stitchingPolicy';

export async function stitchToText(
  chosen: ChosenDraftRef[],
  fetchText: (transcriptionId: string, draftId: string) => Promise<string>
): Promise<string> {
  const parts: string[] = [];
  for (const ref of chosen) {
    const t = await fetchText(ref.transcriptionId, ref.draftId);
    parts.push(t || '');
  }
  return parts.join('\n\n');
}

export function getChosenDraftsForDossier(dossier: Dossier, policy: StitchPolicy): ChosenDraftRef[] {
  return policy(dossier);
}


