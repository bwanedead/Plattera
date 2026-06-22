import type { AgentViewerWorkItem } from '../../../services/agentViewerApi';
import type { WorkItemView } from './viewTypes';
import { firstText, isRecord } from './modelUtils';

export function workItemsToViews(items: AgentViewerWorkItem[]): WorkItemView[] {
  return items.map((item) => {
    const payload = isRecord(item.domain_payload) ? item.domain_payload : {};
    const level = payload.level === 'group' || payload.level === 'unit' ? payload.level : 'item';
    const parentId =
      typeof payload.parent_group_id === 'string'
        ? payload.parent_group_id
        : Array.isArray(item.relation_refs) && item.relation_refs[0]
          ? String(item.relation_refs[0])
          : null;
    return {
      id: item.id,
      title: item.title,
      status: item.status,
      candidateValues: Array.isArray(item.candidate_values) ? item.candidate_values : [],
      determinedValue: item.determined_value ?? null,
      confidence: item.confidence ?? null,
      evidenceRefs: Array.isArray(item.evidence_refs) ? item.evidence_refs.map(String) : [],
      relationRefs: Array.isArray(item.relation_refs) ? item.relation_refs.map(String) : [],
      level,
      parentId,
      domainPayload: payload,
      raw: item,
    };
  });
}

export function summarizeWorkItems(items: WorkItemView[]): {
  open: number;
  blocked: number;
  closed: number;
} {
  let open = 0;
  let blocked = 0;
  let closed = 0;
  for (const item of items) {
    const status = firstText(item.status).toLowerCase();
    if (status.includes('block')) blocked += 1;
    else if (['closed', 'complete', 'completed', 'resolved', 'earned'].some((token) => status.includes(token))) closed += 1;
    else open += 1;
  }
  return { open, blocked, closed };
}
