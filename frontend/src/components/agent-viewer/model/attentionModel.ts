import type { AgentViewerEvent, AgentViewerSnapshot } from '../../../services/agentViewerApi';
import { firstText } from './modelUtils';

export type AttentionItem = {
  ref: string;
  label: string;
  reason: 'artifact' | 'evidence' | 'event' | 'chapter';
};

export function buildAttentionItems(
  snapshot: AgentViewerSnapshot | null,
  events: AgentViewerEvent[],
): AttentionItem[] {
  const out: AttentionItem[] = [];
  const seen = new Set<string>();

  const push = (ref: string, label: string, reason: AttentionItem['reason']) => {
    const trimmed = ref.trim();
    if (!trimmed || seen.has(trimmed)) return;
    seen.add(trimmed);
    out.push({ ref: trimmed, label, reason });
  };

  if (snapshot) {
    for (const artifact of snapshot.artifacts.slice(0, 6)) {
      push(artifact.ref, firstText(artifact.title, artifact.ref), 'artifact');
    }
    for (const chapter of snapshot.chapters) {
      for (const ref of chapter.artifact_refs || []) {
        push(ref, ref, 'chapter');
      }
    }
  }

  for (const event of events.slice(0, 8)) {
    const refs = event.artifact_refs;
    if (!refs || typeof refs !== 'object') continue;
    for (const entry of Object.values(refs)) {
      const path = entry?.artifact_path;
      if (typeof path === 'string') push(path, firstText(event.status?.line1, path), 'event');
    }
  }

  return out.slice(0, 12);
}
