import type { AgentViewerEvent } from '../../services/agentViewerApi';

export function summarizeEventForesight(evt: AgentViewerEvent | null): string {
  if (!evt) return 'I am waiting for the next instruction.';
  const line1 = String(evt.status?.line1 || '');
  if (line1.length > 30) return line1;
  if (evt.event_type === 'done') {
    if (line1.length > 10) return line1;
    return 'I have finished this run.';
  }
  if (evt.event_type === 'human_feedback_needed') {
    const blocking = Boolean(evt.payload?.blocking);
    return blocking
      ? 'Next, I need your decision before proceeding.'
      : 'Feedback requested. I will continue investigating while this is pending.';
  }
  const phase = String(evt.status?.stage || evt.payload?.phase || '').toLowerCase();
  if (phase === 'audit') return 'Next, I will audit the transcript for deterministic issues.';
  if (phase === 'open_spans') return 'Next, I will open localized spans to inspect target clauses.';
  if (phase === 'image_verify') return 'Next, I will verify mapping-critical claims against the source image.';
  if (phase === 'apply') return 'Next, I will apply the candidate edit plan safely.';
  if (phase === 'promote') return 'Next, I will evaluate promotion eligibility for mapping use.';
  if (phase) return `Next, I will continue with ${phase.replace(/_/g, ' ')}.`;
  return 'Next, I will continue with the safest available step.';
}

export function readableArtifactText(data: any): string {
  if (data == null) return '';
  if (typeof data === 'string') return data;
  if (typeof data !== 'object') return String(data);
  const asObj = data as Record<string, any>;
  const lines: string[] = [];
  const findingsList =
    Array.isArray(asObj.findings)
      ? asObj.findings
      : Array.isArray(asObj.report?.findings)
      ? asObj.report.findings
      : null;
  const opsList =
    Array.isArray(asObj.ops)
      ? asObj.ops
      : Array.isArray(asObj.plan?.ops)
      ? asObj.plan.ops
      : null;
  const summaryObj =
    typeof asObj.summary === 'object' && asObj.summary !== null
      ? asObj.summary
      : typeof asObj.report?.summary === 'object' && asObj.report.summary !== null
      ? asObj.report.summary
      : null;

  if (typeof asObj.artifact_type === 'string') {
    lines.push(`Artifact Type: ${asObj.artifact_type}`);
  }
  if (summaryObj) {
    const err = Number((summaryObj as any).error_count ?? (summaryObj as any).errors ?? 0);
    const warn = Number((summaryObj as any).warning_count ?? (summaryObj as any).warnings ?? 0);
    const total = Number((summaryObj as any).total_checks ?? (summaryObj as any).total ?? 0);
    if (Number.isFinite(err) || Number.isFinite(warn) || Number.isFinite(total)) {
      lines.push(`Summary: errors=${Number.isFinite(err) ? err : 0}, warnings=${Number.isFinite(warn) ? warn : 0}, total=${Number.isFinite(total) ? total : 0}`);
    }
  }

  if (Array.isArray(asObj.sections)) {
    lines.push(`Sections: ${asObj.sections.length}`);
    asObj.sections.slice(0, 24).forEach((section: any) => {
      const body = typeof section?.body === 'string' ? section.body.trim() : '';
      if (!body) return;
      lines.push('');
      lines.push(body);
    });
    return lines.join('\n');
  }

  if (Array.isArray(asObj.results)) {
    asObj.results.slice(0, 25).forEach((result: any, idx: number) => {
      lines.push(`\nCheck ${idx + 1}`);
      if (result?.check_id) lines.push(`- ID: ${result.check_id}`);
      if (result?.status) lines.push(`- Status: ${result.status}`);
      if (result?.confidence) lines.push(`- Confidence: ${result.confidence}`);
      if (result?.observed_text) lines.push(`- Observed: ${String(result.observed_text).trim()}`);
      if (result?.reason) lines.push(`- Reason: ${String(result.reason).trim()}`);
    });
    return lines.join('\n').trim();
  }

  if (findingsList) {
    lines.push(`Findings: ${findingsList.length}`);
    findingsList.slice(0, 30).forEach((finding: any, idx: number) => {
      const sev = String(finding?.severity || 'unknown');
      const msg = String(finding?.message || '').trim();
      const kind = String(finding?.finding_type || 'finding');
      lines.push(`${idx + 1}. [${sev}] ${kind}${msg ? ` — ${msg}` : ''}`);
    });
    return lines.join('\n');
  }

  if (opsList) {
    lines.push(`Proposed Edits: ${opsList.length}`);
    opsList.slice(0, 25).forEach((op: any, idx: number) => {
      const opType = String(op?.op_type || 'edit');
      const reason = String(op?.reason || '').trim();
      lines.push(`${idx + 1}. ${opType}${reason ? ` — ${reason}` : ''}`);
    });
    return lines.join('\n');
  }

  for (const [key, value] of Object.entries(asObj)) {
    if (value == null) continue;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      lines.push(`${key}: ${String(value)}`);
    }
  }

  if (lines.length === 0) {
    return 'Structured artifact loaded. No text-friendly fields found in this payload.';
  }
  return lines.join('\n');
}

export function transcriptTextFromArtifact(data: any): string {
  if (!data) return '';
  if (typeof data === 'string') return data;
  if (typeof data !== 'object') return String(data);
  const asObj = data as Record<string, any>;
  if (Array.isArray(asObj.sections)) {
    return asObj.sections
      .map((section: any) => (typeof section?.body === 'string' ? section.body.trim() : ''))
      .filter(Boolean)
      .join('\n\n');
  }
  const directText = typeof asObj.text === 'string' ? asObj.text : '';
  const extracted = typeof asObj.extracted_text === 'string' ? asObj.extracted_text : '';
  return directText || extracted || readableArtifactText(data);
}

export function findLatestRef(events: AgentViewerEvent[], key: string): string | null {
  for (const evt of events) {
    const path = evt?.artifact_refs?.[key]?.artifact_path;
    if (path) return path;
  }
  return null;
}

export function buildLineDiffRows(beforeText: string, afterText: string): Array<{ left: string; right: string; changed: boolean }> {
  const leftLines = (beforeText || '').split('\n');
  const rightLines = (afterText || '').split('\n');
  const max = Math.max(leftLines.length, rightLines.length);
  const rows: Array<{ left: string; right: string; changed: boolean }> = [];
  for (let i = 0; i < max; i += 1) {
    const left = leftLines[i] ?? '';
    const right = rightLines[i] ?? '';
    rows.push({ left, right, changed: left.trim() !== right.trim() });
  }
  return rows;
}

export function extractImagePath(events: AgentViewerEvent[], selectedArtifactJson: any): string | null {
  if (selectedArtifactJson && typeof selectedArtifactJson === 'object') {
    const direct = typeof selectedArtifactJson.image_path === 'string' ? selectedArtifactJson.image_path : '';
    if (direct) return direct;
  }
  for (const evt of events) {
    const phase = String(evt.payload?.phase || '').toLowerCase();
    if (phase !== 'image_verify_result') continue;
    const iv = evt.payload?.image_verification as Record<string, any> | undefined;
    const path = typeof iv?.image_path === 'string' ? iv.image_path : '';
    if (path) return path;
  }
  return null;
}

export function extractImageVerificationResults(events: AgentViewerEvent[], selectedArtifactJson: any): Array<Record<string, any>> {
  if (selectedArtifactJson && typeof selectedArtifactJson === 'object' && Array.isArray((selectedArtifactJson as any).results)) {
    return (selectedArtifactJson as any).results.filter((v: any) => v && typeof v === 'object');
  }
  for (const evt of events) {
    const phase = String(evt.payload?.phase || '').toLowerCase();
    if (phase !== 'image_verify_result') continue;
    const iv = evt.payload?.image_verification as Record<string, any> | undefined;
    const results = Array.isArray(iv?.results) ? iv?.results : [];
    return results.filter((v: any) => v && typeof v === 'object');
  }
  return [];
}

export function renderMetaOf(result: any): Record<string, any> | null {
  if (!result || typeof result !== 'object') return null;
  const meta = (result as any).render_meta;
  return meta && typeof meta === 'object' ? meta : null;
}

export function extractPreviewPolyline(data: any): Array<[number, number]> | null {
  if (!data || typeof data !== 'object') return null;
  const obj = data as Record<string, any>;
  if (Array.isArray(obj.coordinates) && obj.coordinates.length > 1) {
    const coords = obj.coordinates.filter((v: any) => Array.isArray(v) && v.length >= 2).map((v: any) => [Number(v[0]), Number(v[1])] as [number, number]);
    return coords.length > 1 ? coords : null;
  }
  if (Array.isArray(obj.features) && obj.features.length > 0) {
    const feature = obj.features[0];
    const geometry = feature?.geometry;
    const coords = geometry?.coordinates;
    if (Array.isArray(coords) && Array.isArray(coords[0]) && Array.isArray(coords[0][0])) {
      const ring = coords[0].map((v: any) => [Number(v[0]), Number(v[1])] as [number, number]);
      return ring.length > 1 ? ring : null;
    }
    if (Array.isArray(coords) && Array.isArray(coords[0])) {
      const line = coords.map((v: any) => [Number(v[0]), Number(v[1])] as [number, number]);
      return line.length > 1 ? line : null;
    }
  }
  return null;
}

export function collectArtifactCandidates(events: AgentViewerEvent[]): string[] {
  const keyPriority: string[] = [
    'tx_edited_transcript_ref',
    'tx_source_transcript_ref',
    'tx_mapping_pointer_ref',
    'tx_apply_report_ref',
    'tx_edit_plan_ref',
    'tx_image_verify_ref',
    'tx_open_spans_ref',
    'tx_validator_report_ref',
    'ir_ref',
  ];
  const seen = new Set<string>();
  const refs: string[] = [];
  for (const evt of events) {
    const eventRefs = evt.artifact_refs || {};
    for (const key of keyPriority) {
      const path = eventRefs[key]?.artifact_path;
      if (!path || seen.has(path)) continue;
      seen.add(path);
      refs.push(path);
    }
    for (const [, ref] of Object.entries(eventRefs)) {
      const path = ref?.artifact_path;
      if (!path || seen.has(path)) continue;
      seen.add(path);
      refs.push(path);
    }
  }
  return refs;
}

export function extractDecisionLedger(evt: AgentViewerEvent | null, terminalSummary: Record<string, any> | null): Record<string, any> | null {
  const detailLedger = evt?.payload?.detail?.decision_ledger;
  if (detailLedger && typeof detailLedger === 'object') return detailLedger as Record<string, any>;
  const terminalLedger = terminalSummary?.decision_ledger;
  if (terminalLedger && typeof terminalLedger === 'object') return terminalLedger as Record<string, any>;
  return null;
}

export function collectUpstreamCorrectionRequests(events: AgentViewerEvent[]): Array<Record<string, any>> {
  const requests: Array<Record<string, any>> = [];
  const seen = new Set<string>();
  for (const evt of events) {
    if (evt.event_type === 'upstream_correction_request' && evt.payload?.request && typeof evt.payload.request === 'object') {
      const req = evt.payload.request as Record<string, any>;
      const id = String(req.request_id || `${req.reason_code || 'request'}:${req.message || ''}`);
      if (!seen.has(id)) {
        seen.add(id);
        requests.push(req);
      }
    }
    const runPayload = evt.payload?.run;
    if (runPayload && typeof runPayload === 'object' && Array.isArray((runPayload as any).upstream_correction_requests)) {
      for (const req of (runPayload as any).upstream_correction_requests) {
        if (!req || typeof req !== 'object') continue;
        const id = String((req as any).request_id || `${(req as any).reason_code || 'request'}:${(req as any).message || ''}`);
        if (!seen.has(id)) {
          seen.add(id);
          requests.push(req as Record<string, any>);
        }
      }
    }
  }
  return requests;
}
