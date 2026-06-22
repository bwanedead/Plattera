import { extractGenericText } from '../../generic/textExtraction';
import { isRecord } from '../../../model/modelUtils';

export function extractTranscriptDraftText(value: unknown): string | null {
  const generic = extractGenericText(value);
  if (generic) return generic;
  if (!isRecord(value)) return null;

  const draft = value.draft_payload;
  if (isRecord(draft)) {
    const verbatim = draft.source_transcript_verbatim;
    if (typeof verbatim === 'string' && verbatim.trim()) return verbatim;
    const normalized = draft.normalized_or_mapping_transcript;
    if (typeof normalized === 'string' && normalized.trim()) return normalized;
  }

  const lanes = value.lanes;
  if (isRecord(lanes)) {
    for (const lane of Object.values(lanes)) {
      if (typeof lane === 'string' && lane.trim()) return lane;
    }
  }

  return null;
}
