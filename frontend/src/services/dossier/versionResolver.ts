import { Run, Draft } from '../../types/dossier';

function getTranscriptionId(run: Run): string {
  return (run as any)?.transcriptionId || (run as any)?.transcription_id || '';
}

function getBaseTidFromTranscriptionId(transcriptionId: string): string {
  return String(transcriptionId).replace(/_v[12]$/, '');
}

function getDraftPosition(draft: Draft): number {
  return (draft?.position ?? 0) + 1;
}

export function isStrictVersionedId(id: string): boolean {
  return /(_v[12]$|_draft_\d+_v[12]$|_consensus_(llm|alignment)_v[12]$)/.test(String(id));
}

/**
 * Compute a strict versioned ID for a non-consensus draft using precedence:
 * alignment v2 > alignment v1 > raw v2 > raw v1.
 */
export function pickStrictVersionedId(run: Run, draft: Draft): string {
  const transcriptionId = getTranscriptionId(run);
  const baseTid = getBaseTidFromTranscriptionId(transcriptionId);
  const pos = getDraftPosition(draft);
  const versions = ((draft as any)?.metadata?.versions) || {};

  // Alignment precedence first: av2 > av1
  const align = versions?.alignment || {};
  if (align?.v2) return `${baseTid}_draft_${pos}_v2`;
  if (align?.v1) return `${baseTid}_draft_${pos}_v1`;

  // Raw precedence next: v2 > v1
  const raw = versions?.raw || {};
  const head = raw?.head || (raw?.v2 ? 'v2' : 'v1');
  return `${baseTid}_v${pos}_${head}`;
}

/**
 * Compute a strict versioned ID for a consensus draft of the given type.
 * Prefers explicit head when present, otherwise v2 > v1 > base consensus id.
 */
export function pickConsensusStrictId(run: Run, type: 'llm' | 'alignment'): string | null {
  const transcriptionId = getTranscriptionId(run);
  const baseTid = getBaseTidFromTranscriptionId(transcriptionId);

  const drafts = (run?.drafts || []) as Draft[];
  const draft = drafts.find(d => String(d.id).endsWith(`_consensus_${type}`));
  if (!draft) return null;

  const vmeta = ((draft as any)?.metadata?.versions?.consensus || {}) as any;
  const bucket = vmeta?.[type] || {};

  const head = bucket?.head;
  if (head === 'v2' || head === 'v1') {
    return `${baseTid}_consensus_${type}_${head}`;
  }
  if (bucket?.v2) return `${baseTid}_consensus_${type}_v2`;
  if (bucket?.v1) return `${baseTid}_consensus_${type}_v1`;
  return `${baseTid}_consensus_${type}`;
}

/**
 * Return the finals registry's strict draft id if present at the run level, else null.
 */
export function pickRunFinalId(run: Run): string | null {
  const finalId = (run as any)?.metadata?.final_selected_id;
  return typeof finalId === 'string' && finalId.trim() ? finalId : null;
}


