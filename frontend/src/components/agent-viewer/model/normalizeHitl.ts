import type { AgentViewerEvent, AgentViewerHitlPrompt, AgentViewerSnapshot } from '../../../services/agentViewerApi';
import type { NormalizedHitlPrompt } from './viewTypes';
import { firstText, isRecord } from './modelUtils';

export function hitlPromptsFromSnapshot(snapshot: AgentViewerSnapshot | null): NormalizedHitlPrompt[] {
  if (!snapshot) return [];
  return snapshot.hitl_prompts.map((prompt) => snapshotPromptToNormalized(prompt));
}

export function hitlPromptFromEvent(event: AgentViewerEvent): NormalizedHitlPrompt | null {
  if (event.event_type !== 'human_feedback_needed') return null;
  const promptId = firstText(event.payload?.prompt_id);
  if (!promptId) return null;
  const choices = Array.isArray(event.payload?.choices)
    ? event.payload.choices.filter((value): value is string => typeof value === 'string')
    : [];
  const context = isRecord(event.payload?.context) ? event.payload.context : {};
  return {
    promptId,
    blocking: Boolean(event.payload?.blocking),
    question: firstText(event.status?.line1, 'Human feedback needed'),
    detail: firstText(event.status?.line2) || null,
    choices: choices.slice(0, 12),
    evidenceRefs: collectRefs(context.evidence_refs, context.primary_evidence_ref, context.annotated_evidence_ref),
    workItemRefs: collectStringList(context.affected_work_item_refs),
    source: 'event',
    raw: event,
  };
}

export function activeHitlPrompt(
  snapshot: AgentViewerSnapshot | null,
  events: AgentViewerEvent[],
  answeredPromptIds: Set<string>,
): NormalizedHitlPrompt | null {
  for (const event of events) {
    const fromEvent = hitlPromptFromEvent(event);
    if (!fromEvent) continue;
    if (answeredPromptIds.has(fromEvent.promptId)) continue;
    return fromEvent;
  }
  for (const prompt of hitlPromptsFromSnapshot(snapshot)) {
    if (answeredPromptIds.has(prompt.promptId)) continue;
    return prompt;
  }
  return null;
}

function snapshotPromptToNormalized(prompt: AgentViewerHitlPrompt): NormalizedHitlPrompt {
  return {
    promptId: prompt.prompt_id,
    blocking: prompt.blocking,
    question: prompt.question,
    detail: null,
    choices: Array.isArray(prompt.choices) ? prompt.choices : [],
    evidenceRefs: Array.isArray(prompt.evidence_refs) ? prompt.evidence_refs.map(String) : [],
    workItemRefs: Array.isArray(prompt.affected_work_item_refs) ? prompt.affected_work_item_refs.map(String) : [],
    source: 'snapshot',
    raw: prompt,
  };
}

function collectRefs(...sources: unknown[]): string[] {
  const out = new Set<string>();
  for (const source of sources) {
    if (typeof source === 'string' && source.trim()) out.add(source.trim());
    if (Array.isArray(source)) {
      for (const value of source) {
        if (typeof value === 'string' && value.trim()) out.add(value.trim());
      }
    }
  }
  return Array.from(out).slice(0, 12);
}

function collectStringList(raw: unknown): string[] {
  if (!Array.isArray(raw)) return [];
  return raw.map((value) => (typeof value === 'string' ? value.trim() : '')).filter(Boolean).slice(0, 12);
}
