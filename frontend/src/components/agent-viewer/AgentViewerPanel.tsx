import React from 'react';
import {
  getAgentViewerArtifactImageUrl,
  getAgentViewerArtifactJson,
  getAgentViewerFeedback,
  subscribeAgentViewerEvents,
  submitAgentViewerFeedback,
  type AgentViewerEvent,
  type AgentViewerFeedbackEntry,
  type AgentViewerLoopKind,
} from '../../services/agentViewerApi';

interface AgentViewerPanelProps {
  isOpen: boolean;
  loopKind: AgentViewerLoopKind | null;
  runId: string | null;
  sessionKey?: string;
  transcriptionDrafts?: Array<{ id: string; label: string; text: string }>;
  isTranscribing?: boolean;
  onClose: () => void;
}

type ViewerTheme = 'void' | 'space';
type CanvasMode = 'transcription' | 'agent';
type AgentCanvasPage = 'live_draft' | 'diff' | 'verify_image' | 'ops' | 'wip_preview';
type ClosureRequirement = {
  block_reason?: string;
  required_information?: string;
  self_retrievable?: string;
  retrieval_attempted?: boolean;
  retrieval_blocker?: string | null;
  minimal_user_action?: string;
  resolution_options?: string[];
  evidence_refs?: string[];
  attempt_summary?: string;
};
type DecisionLedgerItem = {
  key?: string;
  label?: string;
  state?: string;
  selected_value?: string | null;
  alternatives?: string[];
  blocking?: boolean;
  confidence?: string | number | null;
  closure_requirement?: ClosureRequirement | null;
};

function summarizeEventForesight(evt: AgentViewerEvent | null): string {
  if (!evt) return 'I am waiting for the next instruction.';
  // Prefer dynamic backend message if substantive
  const line1 = String(evt.status?.line1 || '');
  if (line1.length > 30) return line1;
  // For done events, use the backend terminal message
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
  // Fallback to phase-based canned text for old/sparse events
  const phase = String(evt.status?.stage || evt.payload?.phase || '').toLowerCase();
  if (phase === 'audit') return 'Next, I will audit the transcript for deterministic issues.';
  if (phase === 'open_spans') return 'Next, I will open localized spans to inspect target clauses.';
  if (phase === 'image_verify') return 'Next, I will verify mapping-critical claims against the source image.';
  if (phase === 'apply') return 'Next, I will apply the candidate edit plan safely.';
  if (phase === 'promote') return 'Next, I will evaluate promotion eligibility for mapping use.';
  if (phase) return `Next, I will continue with ${phase.replace(/_/g, ' ')}.`;
  return 'Next, I will continue with the safest available step.';
}

const SEVERITY_COLORS: Record<string, string> = {
  error: '#ff6b6b',
  warning: '#d4a83f',
  info: '#8ec5ff',
};

function closureReasonLabel(reason: string): string {
  const r = String(reason || '').toLowerCase();
  if (r === 'ambiguity') return 'Layer 1 Ambiguity';
  if (r === 'contradiction') return 'Layer 2 Contradiction';
  if (r === 'dependency') return 'Layer 3 Dependency';
  return 'Closure Needed';
}

function EventDetailBlock({ evt }: { evt: AgentViewerEvent }) {
  const phase = String(evt.payload?.phase || '').toLowerCase();
  const detail = evt.payload?.detail as Record<string, any> | undefined;
  if (!detail) return null;

  if (phase === 'audit_result' && Array.isArray(detail.top_findings)) {
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {(detail.top_findings as any[]).slice(0, 5).map((f: any, i: number) => (
          <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'baseline', marginBottom: 3 }}>
            <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: SEVERITY_COLORS[f.severity] || '#555', color: '#fff', flexShrink: 0 }}>
              {String(f.severity || 'info').toUpperCase()}
            </span>
            <span style={{ opacity: 0.88 }}>{String(f.message || '').slice(0, 140)}</span>
          </div>
        ))}
      </div>
    );
  }

  if (phase === 'open_spans_result' && Array.isArray(detail.spans)) {
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {(detail.spans as any[]).slice(0, 4).map((s: any, i: number) => (
          <div key={i} style={{ marginBottom: 4, fontFamily: 'monospace', fontSize: 10, opacity: 0.82, background: 'rgba(255,255,255,0.03)', padding: '3px 6px', borderRadius: 4 }}>
            {String(s.text || '').slice(0, 100)}
          </div>
        ))}
      </div>
    );
  }

  if (phase === 'image_verify_result' && Array.isArray(detail.results)) {
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {(detail.results as any[]).slice(0, 5).map((r: any, i: number) => {
          const st = String(r.status || '').toLowerCase();
          const isOk = st === 'confirmed' || st === 'match';
          return (
            <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'baseline', marginBottom: 3 }}>
              <span style={{ fontSize: 10, padding: '1px 5px', borderRadius: 4, background: isOk ? '#2ac477' : '#ff6b6b', color: '#fff', flexShrink: 0 }}>
                {isOk ? 'OK' : 'FAIL'}
              </span>
              <span style={{ opacity: 0.82 }}>{String(r.check_id || '')} — {String(r.observed_text || '').slice(0, 80)}</span>
            </div>
          );
        })}
      </div>
    );
  }

  if ((phase === 'plan_result' || phase === 'apply_result') && Array.isArray(detail.ops_preview || detail.ops)) {
    const ops = (detail.ops_preview || detail.ops || []) as any[];
    return (
      <div style={{ padding: '6px 0', fontSize: 11, lineHeight: 1.4 }}>
        {ops.slice(0, 4).map((op: any, i: number) => (
          <div key={i} style={{ marginBottom: 4 }}>
            <div style={{ fontSize: 10, opacity: 0.6 }}>{String(op.reason || '').slice(0, 80)}</div>
            <div>
              <span style={{ textDecoration: 'line-through', opacity: 0.5 }}>{String(op.original_text || '')}</span>
              {' → '}
              <span style={{ color: '#2ac477' }}>{String(op.replacement_text || '')}</span>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return null;
}

function readableArtifactText(data: any): string {
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

function transcriptTextFromArtifact(data: any): string {
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

function findLatestRef(events: AgentViewerEvent[], key: string): string | null {
  for (const evt of events) {
    const path = evt?.artifact_refs?.[key]?.artifact_path;
    if (path) return path;
  }
  return null;
}

function buildLineDiffRows(beforeText: string, afterText: string): Array<{ left: string; right: string; changed: boolean }> {
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

function extractImagePath(events: AgentViewerEvent[], selectedArtifactJson: any): string | null {
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

function extractImageVerificationResults(events: AgentViewerEvent[], selectedArtifactJson: any): Array<Record<string, any>> {
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

function renderMetaOf(result: any): Record<string, any> | null {
  if (!result || typeof result !== 'object') return null;
  const meta = (result as any).render_meta;
  return meta && typeof meta === 'object' ? meta : null;
}

function extractPreviewPolyline(data: any): Array<[number, number]> | null {
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

function collectArtifactCandidates(events: AgentViewerEvent[]): string[] {
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

function extractDecisionLedger(evt: AgentViewerEvent | null, terminalSummary: Record<string, any> | null): Record<string, any> | null {
  const detailLedger = evt?.payload?.detail?.decision_ledger;
  if (detailLedger && typeof detailLedger === 'object') return detailLedger as Record<string, any>;
  const terminalLedger = terminalSummary?.decision_ledger;
  if (terminalLedger && typeof terminalLedger === 'object') return terminalLedger as Record<string, any>;
  return null;
}

function collectUpstreamCorrectionRequests(events: AgentViewerEvent[]): Array<Record<string, any>> {
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

async function loadBestArtifactJson(startRef: string, candidates: string[]): Promise<{ ref: string; json: any }> {
  const queue = [startRef, ...candidates.filter((v) => v && v !== startRef)];
  const visited = new Set<string>();
  let lastError: Error | null = null;

  while (queue.length) {
    const ref = queue.shift() as string;
    if (!ref || visited.has(ref)) continue;
    visited.add(ref);
    try {
      const payload = await getAgentViewerArtifactJson(ref);
      const data = payload?.json;
      // If this is a pointer artifact, follow transcript refs automatically.
      if (data && typeof data === 'object' && !Array.isArray(data)) {
        const transcriptRef = typeof (data as any).transcript_ref === 'string' ? String((data as any).transcript_ref) : '';
        const sourceRef = typeof (data as any).source_transcript_ref === 'string' ? String((data as any).source_transcript_ref) : '';
        if (transcriptRef && !visited.has(transcriptRef)) {
          queue.unshift(transcriptRef);
          continue;
        }
        if (sourceRef && !visited.has(sourceRef)) {
          queue.unshift(sourceRef);
          continue;
        }
      }
      return { ref, json: data };
    } catch (error) {
      lastError = error instanceof Error ? error : new Error('Failed to open artifact');
    }
  }

  throw lastError || new Error('Failed to open artifact');
}

export const AgentViewerPanel: React.FC<AgentViewerPanelProps> = ({
  isOpen,
  loopKind,
  runId,
  sessionKey,
  transcriptionDrafts = [],
  isTranscribing = false,
  onClose,
}) => {
  const [events, setEvents] = React.useState<AgentViewerEvent[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [feedbackEntries, setFeedbackEntries] = React.useState<AgentViewerFeedbackEntry[]>([]);
  const [feedbackNote, setFeedbackNote] = React.useState('');
  const [feedbackBusy, setFeedbackBusy] = React.useState(false);
  const [feedbackError, setFeedbackError] = React.useState<string | null>(null);
  const [promptReceipt, setPromptReceipt] = React.useState<string | null>(null);
  const [isHydratingReplay, setIsHydratingReplay] = React.useState(false);
  const replayHydratingRef = React.useRef(false);
  const [decisionOtherByKey, setDecisionOtherByKey] = React.useState<Record<string, string>>({});
  const [canvasMode, setCanvasMode] = React.useState<CanvasMode>('transcription');
  const [selectedDraftIndex, setSelectedDraftIndex] = React.useState(0);
  const [theme, setTheme] = React.useState<ViewerTheme>('void');
  const [lensing, setLensing] = React.useState<{ x: number; y: number; active: boolean }>({ x: 50, y: 50, active: false });
  const [selectedArtifactRef, setSelectedArtifactRef] = React.useState<string | null>(null);
  const [selectedArtifactJson, setSelectedArtifactJson] = React.useState<any>(null);
  const [artifactError, setArtifactError] = React.useState<string | null>(null);
  const [loadingArtifact, setLoadingArtifact] = React.useState(false);
  const [canvasPageIndex, setCanvasPageIndex] = React.useState(0);
  const [sourceTranscriptText, setSourceTranscriptText] = React.useState('');
  const [editedTranscriptText, setEditedTranscriptText] = React.useState('');
  const [selectedVerifyResultIndex, setSelectedVerifyResultIndex] = React.useState(0);

  const activeLoopKind = loopKind ?? null;
  const activeRunId = typeof runId === 'string' && runId.trim() ? runId : null;
  const hasActiveRun = Boolean(activeLoopKind && activeRunId);

  React.useEffect(() => {
    if (hasActiveRun) setCanvasMode('agent');
  }, [hasActiveRun]);

  React.useEffect(() => {
    if (selectedDraftIndex < transcriptionDrafts.length) return;
    setSelectedDraftIndex(0);
  }, [selectedDraftIndex, transcriptionDrafts.length]);

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) return;
    setEvents([]);
    setConnected(false);
    setIsHydratingReplay(true);
    replayHydratingRef.current = true;
    const replayTimer = window.setTimeout(() => {
      replayHydratingRef.current = false;
      setIsHydratingReplay(false);
    }, 1400);
    const unsubscribe = subscribeAgentViewerEvents(
      activeLoopKind,
      activeRunId,
      (event) => {
        setConnected(true);
        const taggedEvent =
          replayHydratingRef.current
            ? {
                ...event,
                payload: {
                  ...(event.payload || {}),
                  __replay: true,
                },
              }
            : event;
        setEvents((prev) => [taggedEvent, ...prev].slice(0, 250));
      },
      () => setConnected(false),
    );
    return () => {
      window.clearTimeout(replayTimer);
      replayHydratingRef.current = false;
      setIsHydratingReplay(false);
      unsubscribe();
    };
  }, [isOpen, activeLoopKind, activeRunId]);

  React.useEffect(() => {
    if (!isOpen) return;
    const endpoint = 'http://127.0.0.1:8000/api/logs/frontend';
    const postLog = (level: string, args: any[]) => {
      try {
        const text = args
          .map((v) => {
            if (typeof v === 'string') return v;
            try {
              return JSON.stringify(v);
            } catch {
              return String(v);
            }
          })
          .join(' ');
        void fetch(endpoint, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            level,
            message: text.slice(0, 3800),
            source: 'agent_viewer_client',
            ts: Date.now() / 1000,
          }),
        });
      } catch {
        // ignore
      }
    };

    const originalWarn = console.warn;
    const originalError = console.error;
    console.warn = (...args: any[]) => {
      postLog('WARNING', args);
      originalWarn(...args);
    };
    console.error = (...args: any[]) => {
      postLog('ERROR', args);
      originalError(...args);
    };

    const onWindowError = (evt: ErrorEvent) => {
      postLog('ERROR', [evt.message, evt.filename, evt.lineno, evt.colno]);
    };
    window.addEventListener('error', onWindowError);

    return () => {
      console.warn = originalWarn;
      console.error = originalError;
      window.removeEventListener('error', onWindowError);
    };
  }, [isOpen]);

  React.useEffect(() => {
    if (!isOpen) return;
    setEvents([]);
    setConnected(false);
    setSelectedArtifactRef(null);
    setSelectedArtifactJson(null);
    setArtifactError(null);
    setFeedbackEntries([]);
    setFeedbackNote('');
    setFeedbackError(null);
    setPromptReceipt(null);
    setCanvasPageIndex(0);
    setSourceTranscriptText('');
    setEditedTranscriptText('');
    setSelectedVerifyResultIndex(0);
  }, [isOpen, sessionKey]);

  React.useEffect(() => {
    if (!isOpen) return;
    if (!isTranscribing) return;
    if (hasActiveRun) return;
    setEvents([]);
    setConnected(false);
    setSelectedArtifactRef(null);
    setSelectedArtifactJson(null);
    setArtifactError(null);
  }, [isOpen, isTranscribing, hasActiveRun]);

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) return;
    let cancelled = false;
    (async () => {
      try {
        const feedback = await getAgentViewerFeedback(activeLoopKind, activeRunId);
        if (!cancelled) {
          setFeedbackEntries(Array.isArray(feedback.entries) ? feedback.entries : []);
        }
      } catch {
        if (!cancelled) setFeedbackEntries([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeLoopKind, activeRunId]);

  const orderedEvents = React.useMemo(() => {
    const sorted = [...events];
    sorted.sort((a, b) => {
      const at = typeof a.timestamp_epoch_seconds === 'number' ? a.timestamp_epoch_seconds : -1;
      const bt = typeof b.timestamp_epoch_seconds === 'number' ? b.timestamp_epoch_seconds : -1;
      if (at !== bt) return bt - at;
      const as = typeof a.seq === 'number' ? a.seq : -1;
      const bs = typeof b.seq === 'number' ? b.seq : -1;
      return bs - as;
    });
    return sorted;
  }, [events]);

  const doneEvent = React.useMemo(() => orderedEvents.find((evt) => evt.event_type === 'done') || null, [orderedEvents]);
  const currentEvent = doneEvent || orderedEvents.find((evt) => String(evt.payload?.stream_kind || 'narration') !== 'ticker') || orderedEvents[0] || null;
  const detailEvent = React.useMemo(
    () => orderedEvents.find((evt) => evt?.payload?.detail && typeof evt.payload.detail === 'object') || null,
    [orderedEvents],
  );
  const isRunTerminal = Boolean(doneEvent);
  const terminalStatus: 'completed' | 'needs_review' | 'failed' | null = isRunTerminal
    ? (() => {
        const doneEvt = doneEvent;
        const stage = String(doneEvt?.status?.stage || doneEvt?.payload?.phase || '').toLowerCase();
        if (stage === 'completed') return 'completed';
        if (stage === 'failed') return 'failed';
        return 'needs_review';
      })()
    : null;
  const currentStatusText = summarizeEventForesight(currentEvent);
  const terminalSummary = React.useMemo(() => {
    const raw = doneEvent?.payload?.summary;
    return raw && typeof raw === 'object' ? (raw as Record<string, any>) : null;
  }, [doneEvent]);
  const unresolvedRequirementsCount = React.useMemo(() => {
    if (!terminalSummary) return 0;
    const unresolved = terminalSummary.unresolved_closure_requirements;
    return Array.isArray(unresolved) ? unresolved.length : 0;
  }, [terminalSummary]);
  const decisionLedger = React.useMemo(
    () => extractDecisionLedger(detailEvent, terminalSummary),
    [detailEvent, terminalSummary],
  );
  const decisionItems = React.useMemo(
    () => (Array.isArray(decisionLedger?.items) ? (decisionLedger?.items as DecisionLedgerItem[]) : []),
    [decisionLedger],
  );
  const decisionSummary = React.useMemo(
    () => (decisionLedger && typeof decisionLedger.summary === 'object' ? (decisionLedger.summary as Record<string, any>) : null),
    [decisionLedger],
  );
  const upstreamCorrectionRequests = React.useMemo(
    () => collectUpstreamCorrectionRequests(orderedEvents),
    [orderedEvents],
  );

  const activeFeedbackPrompt = React.useMemo(() => {
    if (isRunTerminal) return null;
    for (const evt of orderedEvents) {
      if (evt.event_type !== 'human_feedback_needed') continue;
      const promptId = typeof evt.payload?.prompt_id === 'string' ? evt.payload.prompt_id : '';
      if (!promptId) continue;
      const alreadyAnswered = feedbackEntries.some((entry) => String(entry.prompt_id || '') === promptId);
      if (alreadyAnswered) continue;
      const choices = Array.isArray(evt.payload?.choices) ? evt.payload.choices.filter((c: any) => typeof c === 'string') : [];
      return {
        promptId,
        blocking: Boolean(evt.payload?.blocking),
        line1: String(evt.status?.line1 || 'Human feedback needed'),
        line2: String(evt.status?.line2 || ''),
        choices: choices.slice(0, 8),
      };
    }
    return null;
  }, [orderedEvents, isRunTerminal, feedbackEntries]);

  const activePromptSatisfied = React.useMemo(() => {
    if (!activeFeedbackPrompt?.promptId) return false;
    return feedbackEntries.some((entry) => String(entry.prompt_id || '') === activeFeedbackPrompt.promptId);
  }, [activeFeedbackPrompt, feedbackEntries]);

  const recentFeedbackEntries = React.useMemo(() => feedbackEntries.slice(0, 5), [feedbackEntries]);

  React.useEffect(() => {
    if (activeFeedbackPrompt) setPromptReceipt(null);
  }, [activeFeedbackPrompt]);

  const artifactCandidates = React.useMemo(() => collectArtifactCandidates(orderedEvents), [orderedEvents]);
  const sourceTranscriptRef = React.useMemo(() => findLatestRef(orderedEvents, 'tx_source_transcript_ref'), [orderedEvents]);
  const editedTranscriptRef = React.useMemo(() => findLatestRef(orderedEvents, 'tx_edited_transcript_ref'), [orderedEvents]);
  const transcriptDiffRows = React.useMemo(
    () => buildLineDiffRows(sourceTranscriptText, editedTranscriptText),
    [sourceTranscriptText, editedTranscriptText],
  );
  const activeImagePath = React.useMemo(
    () => extractImagePath(orderedEvents, selectedArtifactJson),
    [orderedEvents, selectedArtifactJson],
  );
  const imageVerifyResults = React.useMemo(
    () => extractImageVerificationResults(orderedEvents, selectedArtifactJson),
    [orderedEvents, selectedArtifactJson],
  );
  const selectedVerifyResult = imageVerifyResults[Math.min(selectedVerifyResultIndex, Math.max(imageVerifyResults.length - 1, 0))] || null;
  const selectedVerifyMeta = renderMetaOf(selectedVerifyResult);
  const verifyOriginalSize = React.useMemo(() => {
    const withMeta = imageVerifyResults.find((v) => renderMetaOf(v)?.original_size);
    const size = renderMetaOf(withMeta)?.original_size;
    if (Array.isArray(size) && size.length >= 2) return [Number(size[0]) || 1000, Number(size[1]) || 1000] as [number, number];
    return [1000, 1000] as [number, number];
  }, [imageVerifyResults]);
  const activeImageUrl = React.useMemo(
    () => (activeImagePath ? getAgentViewerArtifactImageUrl(activeImagePath) : null),
    [activeImagePath],
  );
  const previewPolyline = React.useMemo(
    () => extractPreviewPolyline(selectedArtifactJson),
    [selectedArtifactJson],
  );
  const previewPathD = React.useMemo(() => {
    if (!previewPolyline || previewPolyline.length < 2) return '';
    const xs = previewPolyline.map((p) => p[0]);
    const ys = previewPolyline.map((p) => p[1]);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = Math.max(1e-6, maxX - minX);
    const height = Math.max(1e-6, maxY - minY);
    const pad = 24;
    const inner = 1000 - pad * 2;
    return previewPolyline
      .map(([x, y], idx) => {
        const nx = pad + ((x - minX) / width) * inner;
        const ny = 1000 - (pad + ((y - minY) / height) * inner);
        return `${idx === 0 ? 'M' : 'L'} ${nx.toFixed(2)} ${ny.toFixed(2)}`;
      })
      .join(' ');
  }, [previewPolyline]);

  const availableCanvasPages = React.useMemo(() => {
    const pages: Array<{ id: AgentCanvasPage; label: string }> = [{ id: 'live_draft', label: 'Live Draft' }];
    if (sourceTranscriptText || editedTranscriptText) pages.push({ id: 'diff', label: 'Compare' });
    if (activeImageUrl) pages.push({ id: 'verify_image', label: 'Image Verify' });
    if (selectedArtifactJson && typeof selectedArtifactJson === 'object') {
      const obj = selectedArtifactJson as Record<string, any>;
      if (Array.isArray(obj.ops) || Array.isArray(obj.plan?.ops) || Array.isArray(obj.results)) {
        pages.push({ id: 'ops', label: 'Ops/Checks' });
      }
    }
    if (previewPolyline || findLatestRef(orderedEvents, 'ir_ref')) pages.push({ id: 'wip_preview', label: 'WIP Preview' });
    return pages;
  }, [activeImageUrl, editedTranscriptText, orderedEvents, previewPolyline, selectedArtifactJson, sourceTranscriptText]);

  const activeCanvasPage = availableCanvasPages[Math.min(canvasPageIndex, Math.max(availableCanvasPages.length - 1, 0))]?.id ?? 'live_draft';

  React.useEffect(() => {
    if (canvasPageIndex < availableCanvasPages.length) return;
    setCanvasPageIndex(0);
  }, [availableCanvasPages.length, canvasPageIndex]);

  React.useEffect(() => {
    if (selectedVerifyResultIndex < imageVerifyResults.length) return;
    setSelectedVerifyResultIndex(0);
  }, [imageVerifyResults.length, selectedVerifyResultIndex]);

  React.useEffect(() => {
    if (canvasMode !== 'agent') return;
    if (!artifactCandidates.length) return;
    const preferredRef = artifactCandidates[0];
    if (!selectedArtifactRef || !artifactCandidates.includes(selectedArtifactRef)) {
      setSelectedArtifactRef(preferredRef);
    }
  }, [canvasMode, artifactCandidates, selectedArtifactRef]);

  React.useEffect(() => {
    if (!selectedArtifactRef) return;
    let cancelled = false;
    setLoadingArtifact(true);
    setArtifactError(null);
    (async () => {
      try {
        const loaded = await loadBestArtifactJson(selectedArtifactRef, artifactCandidates);
        if (!cancelled) {
          setSelectedArtifactRef(loaded.ref);
          setSelectedArtifactJson(loaded.json ?? null);
        }
      } catch (error) {
        if (!cancelled) {
          setSelectedArtifactJson(null);
          setArtifactError(error instanceof Error ? error.message : 'Failed to open artifact');
        }
      } finally {
        if (!cancelled) setLoadingArtifact(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selectedArtifactRef, artifactCandidates]);

  React.useEffect(() => {
    let cancelled = false;
    const loadTranscriptRef = async (ref: string | null, setter: (value: string) => void) => {
      if (!ref) {
        setter('');
        return;
      }
      try {
        const payload = await getAgentViewerArtifactJson(ref);
        if (!cancelled) setter(transcriptTextFromArtifact(payload?.json));
      } catch {
        if (!cancelled) setter('');
      }
    };
    void loadTranscriptRef(sourceTranscriptRef, setSourceTranscriptText);
    void loadTranscriptRef(editedTranscriptRef, setEditedTranscriptText);
    return () => {
      cancelled = true;
    };
  }, [sourceTranscriptRef, editedTranscriptRef]);

  const submitFeedback = React.useCallback(async (choice?: string) => {
    if (!activeLoopKind || !activeRunId) return;
    setFeedbackBusy(true);
    setFeedbackError(null);
    setPromptReceipt(null);
    const activePromptId = activeFeedbackPrompt?.promptId || null;
    try {
      const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
        prompt_id: activePromptId,
        choice: choice || null,
        note: feedbackNote.trim() || null,
        metadata: {
          canvas_mode: canvasMode,
          event_count: orderedEvents.length,
        },
      });
      setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      if (activePromptId) {
        setPromptReceipt(`Received ${choice || 'feedback'}; queued for next checkpoint.`);
        setEvents((prev) => [
          {
            protocol: 'agent_viewer_event_v1',
            loop_kind: activeLoopKind,
            run_id: activeRunId,
            seq: Date.now(),
            iteration: null,
            timestamp_epoch_seconds: Math.floor(Date.now() / 1000),
            event_type: 'human_feedback',
            status: {
              stage: 'human_feedback',
              line1: 'Feedback received and queued',
              line2: choice || null,
            },
            artifact_refs: {},
            payload: {
              phase: 'human_feedback_received',
              stream_kind: 'narration',
              prompt_id: activePromptId,
              choice: choice || null,
            },
          },
          ...prev,
        ].slice(0, 250));
      }
      setFeedbackNote('');
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : 'Failed to submit feedback');
    } finally {
      setFeedbackBusy(false);
    }
  }, [activeLoopKind, activeRunId, activeFeedbackPrompt, feedbackNote, canvasMode, orderedEvents.length]);

  const resendFeedbackEntry = React.useCallback(
    async (entry: AgentViewerFeedbackEntry) => {
      if (!activeLoopKind || !activeRunId) return;
      setFeedbackBusy(true);
      setFeedbackError(null);
      try {
        const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
          prompt_id: entry.prompt_id || null,
          choice: entry.choice || null,
          note: entry.note || null,
          metadata: {
            ...(entry.metadata || {}),
            action: 'resend_feedback_entry',
          },
        });
        setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to resend feedback');
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeLoopKind, activeRunId],
  );

  const requestDecisionReview = React.useCallback(
    async (decisionKey: string) => {
      if (!activeLoopKind || !activeRunId) return;
      setFeedbackBusy(true);
      setFeedbackError(null);
      try {
        const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
          prompt_id: null,
          choice: null,
          note: `Please re-check decision key: ${decisionKey}`,
          metadata: {
            action: 'review_again',
            decision_key: decisionKey,
            source: 'decision_ledger_panel',
          },
        });
        setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to submit decision review');
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeLoopKind, activeRunId],
  );

  const submitDecisionResolution = React.useCallback(
    async (decisionKey: string, choice: string | null, extraNote?: string | null) => {
      if (!activeLoopKind || !activeRunId) return;
      const key = String(decisionKey || '').trim();
      if (!key) return;
      const chosen = choice ? String(choice).trim() : '';
      const otherRaw = String(decisionOtherByKey[key] || '').trim();
      const noteParts = [
        chosen ? `Resolved ${key} as: ${chosen}` : '',
        extraNote ? String(extraNote).trim() : '',
        !chosen && otherRaw ? `Resolved ${key} as: ${otherRaw}` : '',
      ].filter(Boolean);
      setFeedbackBusy(true);
      setFeedbackError(null);
      try {
        const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
          prompt_id: null,
          choice: chosen || null,
          note: noteParts.length ? noteParts.join(' | ') : null,
          metadata: {
            action: 'resolve_closure_requirement',
            decision_key: key,
            resolved_value: chosen || otherRaw || null,
            source: 'closure_requirement_panel',
          },
        });
        setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
        if (!chosen) {
          setDecisionOtherByKey((prev) => ({ ...prev, [key]: '' }));
        }
      } catch (error) {
        setFeedbackError(error instanceof Error ? error.message : 'Failed to submit closure resolution');
      } finally {
        setFeedbackBusy(false);
      }
    },
    [activeLoopKind, activeRunId, decisionOtherByKey],
  );

  if (!isOpen) return null;

  const isSpaceTheme = theme === 'space';
  const overlayBackground = isSpaceTheme ? 'rgba(0,0,0,0.88)' : 'rgba(0,0,0,0.82)';
  const panelBackground = isSpaceTheme
    ? 'radial-gradient(circle at 20% 20%, rgba(22,27,45,0.82), #000 52%), radial-gradient(circle at 80% 70%, rgba(12,20,38,0.55), #000 60%)'
    : '#000000';
  const headerBackground = isSpaceTheme
    ? 'linear-gradient(180deg, rgba(8,12,22,0.95), rgba(2,2,2,0.98))'
    : '#020202';

  const lensX = lensing.x.toFixed(2);
  const lensY = lensing.y.toFixed(2);
  const lensMask = `radial-gradient(180px circle at ${lensX}% ${lensY}%, rgba(255,255,255,0.98) 0%, rgba(255,255,255,0.45) 40%, rgba(255,255,255,0.12) 62%, transparent 80%)`;
  const lensShiftX = ((lensing.x - 50) * 0.28).toFixed(2);
  const lensShiftY = ((lensing.y - 50) * 0.28).toFixed(2);

  const floatingHistory = orderedEvents.slice(0, 14).map((evt, idx) => ({
    idx,
    text: summarizeEventForesight(evt),
    iteration: evt.iteration,
    isCurrent: idx === 0,
    isTicker: String(evt.payload?.stream_kind || 'narration') === 'ticker',
    isReplay: Boolean(evt.payload?.__replay),
  }));

  return (
    <div
      className="agent-viewer-shell"
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 12000,
        background: overlayBackground,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 14,
      }}
      onClick={onClose}
    >
      <style>
        {`
          .agent-viewer-shell, .agent-viewer-shell * { color: #e8edf7; }
          .agent-viewer-shell button { color: #e8edf7; background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.2); }
          .agent-viewer-shell button:disabled { opacity: 0.6; cursor: not-allowed; }
          .agent-viewer-shell textarea { color: #e8edf7; }
          .agent-viewer-shell textarea::placeholder { color: rgba(232,237,247,0.6); }
        `}
      </style>

      <div
        style={{
          width: 'min(1500px, 97vw)',
          height: 'min(920px, 95vh)',
          background: panelBackground,
          border: '1px solid rgba(255,255,255,0.16)',
          borderRadius: 12,
          overflow: 'hidden',
          display: 'grid',
          gridTemplateRows: '48px 1fr',
          position: 'relative',
        }}
        onMouseMove={(e) => {
          if (!isSpaceTheme) return;
          const rect = e.currentTarget.getBoundingClientRect();
          if (!rect.width || !rect.height) return;
          const x = ((e.clientX - rect.left) / rect.width) * 100;
          const y = ((e.clientY - rect.top) / rect.height) * 100;
          setLensing({ x: Math.max(0, Math.min(100, x)), y: Math.max(0, Math.min(100, y)), active: true });
        }}
        onMouseLeave={() => setLensing((prev) => ({ ...prev, active: false }))}
        onClick={(e) => e.stopPropagation()}
      >
        {isSpaceTheme && (
          <>
            <div
              aria-hidden
              style={{
                position: 'absolute',
                inset: 0,
                pointerEvents: 'none',
                opacity: 0.3,
                backgroundImage:
                  'radial-gradient(rgba(255,255,255,0.9) 0.7px, transparent 0.7px), radial-gradient(rgba(165,197,255,0.7) 0.7px, transparent 0.7px)',
                backgroundSize: '28px 28px, 46px 46px',
                backgroundPosition: '0 0, 13px 21px',
              }}
            />
            <div
              aria-hidden
              style={{
                position: 'absolute',
                inset: 0,
                pointerEvents: 'none',
                opacity: lensing.active ? 0.22 : 0,
                transition: 'opacity 160ms ease-out',
                backgroundImage:
                  'radial-gradient(rgba(255,255,255,0.95) 0.75px, transparent 0.75px), radial-gradient(rgba(165,197,255,0.72) 0.75px, transparent 0.75px)',
                backgroundSize: '23px 23px, 39px 39px',
                backgroundPosition: `${lensShiftX}px ${lensShiftY}px, ${13 + Number(lensShiftX)}px ${21 + Number(lensShiftY)}px`,
                WebkitMaskImage: lensMask,
                maskImage: lensMask,
                filter: 'contrast(1.02)',
              }}
            />
          </>
        )}

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 12px',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            background: headerBackground,
            zIndex: 1,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <strong style={{ fontSize: 13 }}>Agent Viewer</strong>
            <button onClick={() => setTheme((t) => (t === 'void' ? 'space' : 'void'))} style={{ fontSize: 11, borderRadius: 999, padding: '3px 8px' }}>
              Theme: {theme === 'void' ? 'Void' : 'Space'}
            </button>
            <button onClick={() => setCanvasMode('transcription')} style={{ fontSize: 11, borderRadius: 999, padding: '3px 8px', opacity: canvasMode === 'transcription' ? 1 : 0.72 }}>
              Transcription
            </button>
            <button onClick={() => setCanvasMode('agent')} disabled={!hasActiveRun} style={{ fontSize: 11, borderRadius: 999, padding: '3px 8px', opacity: canvasMode === 'agent' ? 1 : 0.72 }}>
              Agent
            </button>
            <span style={{ fontSize: 11, opacity: 0.8 }}>{activeLoopKind ?? 'idle'}</span>
            <span style={{ fontSize: 11, opacity: 0.72 }}>{activeRunId ?? 'no active run'}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, background: connected ? '#2ac477' : '#d4a83f' }} />
            <span style={{ fontSize: 11, opacity: 0.82 }}>{hasActiveRun ? (connected ? 'Live' : 'Disconnected') : (isTranscribing ? 'Transcribing' : 'Idle')}</span>
            <button
              onClick={onClose}
              aria-label="Close Agent Viewer"
              title="Close"
              style={{ width: 30, height: 30, borderRadius: 999, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, lineHeight: 1, fontWeight: 600, padding: 0 }}
            >
              ×
            </button>
          </div>
        </div>

        {canvasMode === 'transcription' && (
          <div style={{ minHeight: 0, padding: 14, display: 'flex', flexDirection: 'column', gap: 12, zIndex: 1 }}>
            {transcriptionDrafts.length === 0 ? (
              <div style={{ flex: 1, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10, background: 'rgba(255,255,255,0.01)' }}>
                <div style={{ fontSize: 13, opacity: 0.86 }}>{isTranscribing ? 'Waiting for transcription drafts…' : 'No transcription artifact loaded yet.'}</div>
                <div style={{ fontSize: 11, opacity: 0.68 }}>Keep this viewer open. Drafts will appear here as they complete.</div>
              </div>
            ) : (
              <>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ fontSize: 12, opacity: 0.8 }}>Draft {selectedDraftIndex + 1} of {transcriptionDrafts.length}</div>
                  <div style={{ display: 'flex', gap: 6 }}>
                    <button onClick={() => setSelectedDraftIndex((v) => Math.max(0, v - 1))} disabled={selectedDraftIndex <= 0}>◀</button>
                    <button onClick={() => setSelectedDraftIndex((v) => Math.min(transcriptionDrafts.length - 1, v + 1))} disabled={selectedDraftIndex >= transcriptionDrafts.length - 1}>▶</button>
                  </div>
                </div>
                <div style={{ fontSize: 12, opacity: 0.85, padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.01)' }}>
                  {transcriptionDrafts[selectedDraftIndex]?.label || `Draft ${selectedDraftIndex + 1}`}
                </div>
                <pre style={{ margin: 0, flex: 1, minHeight: 0, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.45, padding: 12, borderRadius: 10, border: '1px solid rgba(255,255,255,0.09)', background: 'rgba(255,255,255,0.015)' }}>
                  {transcriptionDrafts[selectedDraftIndex]?.text || ''}
                </pre>
              </>
            )}
          </div>
        )}

        {canvasMode === 'agent' && (
          <div style={{ minHeight: 0, zIndex: 1, position: 'relative' }}>
            <div style={{ position: 'absolute', inset: '12px 360px 78px 12px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(0,0,0,0.28)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
              <div style={{ padding: '6px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                {currentEvent && (
                  <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: 'rgba(142,197,255,0.15)', border: '1px solid rgba(142,197,255,0.25)' }}>
                    {String(currentEvent.payload?.phase || currentEvent.status?.stage || 'idle').replace(/_/g, ' ')}
                  </span>
                )}
                {typeof currentEvent?.iteration === 'number' && (
                  <span style={{ fontSize: 10, opacity: 0.6 }}>iter {currentEvent.iteration}</span>
                )}
                <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
                  <button onClick={() => setCanvasPageIndex((v) => Math.max(0, v - 1))} disabled={canvasPageIndex <= 0} style={{ fontSize: 11, padding: '2px 8px' }}>◀</button>
                  <span style={{ fontSize: 11, opacity: 0.84 }}>
                    {availableCanvasPages[canvasPageIndex]?.label || 'Live Draft'}
                  </span>
                  <button onClick={() => setCanvasPageIndex((v) => Math.min(availableCanvasPages.length - 1, v + 1))} disabled={canvasPageIndex >= availableCanvasPages.length - 1} style={{ fontSize: 11, padding: '2px 8px' }}>▶</button>
                </div>
              </div>

              <div style={{ flex: 1, overflow: 'auto', padding: 14 }}>
                {activeCanvasPage === 'live_draft' && (
                  <>
                    {loadingArtifact && <div style={{ fontSize: 12, opacity: 0.86 }}>Loading latest artifact…</div>}
                    {artifactError && <div style={{ fontSize: 12, color: '#ff9aa0' }}>{artifactError}</div>}
                    {!loadingArtifact && !artifactError && !selectedArtifactJson && (
                      <div style={{ fontSize: 12, opacity: 0.72 }}>No artifact loaded yet. Waiting for agent outputs…</div>
                    )}
                    {!loadingArtifact && !selectedArtifactJson && transcriptionDrafts.length > 0 && (
                      <div style={{ marginTop: 10 }}>
                        <div style={{ fontSize: 11, opacity: 0.72, marginBottom: 6 }}>
                          Fallback view: latest transcription draft
                        </div>
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
                          {transcriptionDrafts[Math.min(selectedDraftIndex, transcriptionDrafts.length - 1)]?.text || ''}
                        </pre>
                      </div>
                    )}
                    {!loadingArtifact && !artifactError && selectedArtifactJson && (
                      <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
                        {transcriptTextFromArtifact(selectedArtifactJson)}
                      </pre>
                    )}
                  </>
                )}

                {activeCanvasPage === 'diff' && (
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                    <div>
                      <div style={{ fontSize: 11, opacity: 0.75, marginBottom: 6 }}>Source</div>
                      <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, overflow: 'hidden' }}>
                        {transcriptDiffRows.slice(0, 300).map((row, idx) => (
                          <div key={`l-${idx}`} style={{ padding: '3px 8px', fontSize: 11, lineHeight: 1.35, background: row.changed ? 'rgba(255,107,107,0.10)' : 'transparent' }}>
                            {row.left || ' '}
                          </div>
                        ))}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: 11, opacity: 0.75, marginBottom: 6 }}>Edited</div>
                      <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, overflow: 'hidden' }}>
                        {transcriptDiffRows.slice(0, 300).map((row, idx) => (
                          <div key={`r-${idx}`} style={{ padding: '3px 8px', fontSize: 11, lineHeight: 1.35, background: row.changed ? 'rgba(42,196,119,0.14)' : 'transparent' }}>
                            {row.right || ' '}
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {activeCanvasPage === 'verify_image' && (
                  <div style={{ display: 'grid', gridTemplateRows: '1fr auto', height: '100%', gap: 10 }}>
                    {activeImageUrl ? (
                      <div style={{ borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.02)', overflow: 'hidden' }}>
                        <svg viewBox={`0 0 ${verifyOriginalSize[0]} ${verifyOriginalSize[1]}`} style={{ width: '100%', maxHeight: 520 }}>
                          <image href={activeImageUrl} x={0} y={0} width={verifyOriginalSize[0]} height={verifyOriginalSize[1]} preserveAspectRatio="xMidYMid meet" />
                          {imageVerifyResults.map((result: any, idx: number) => {
                            const meta = renderMetaOf(result);
                            const crop = meta?.crop_box;
                            if (!crop || typeof crop !== 'object') return null;
                            const isSelected = idx === Math.min(selectedVerifyResultIndex, imageVerifyResults.length - 1);
                            const st = String(result?.status || '').toLowerCase();
                            const stroke = st === 'match' || st === 'confirmed' ? '#2ac477' : st === 'mismatch' || st === 'rejected' ? '#ff6b6b' : '#d4a83f';
                            return (
                              <g key={`crop-${idx}`}>
                                <rect
                                  x={Number(crop.x) || 0}
                                  y={Number(crop.y) || 0}
                                  width={Math.max(1, Number(crop.width) || 0)}
                                  height={Math.max(1, Number(crop.height) || 0)}
                                  fill={isSelected ? `${stroke}22` : `${stroke}12`}
                                  stroke={stroke}
                                  strokeWidth={isSelected ? 3 : 1.5}
                                />
                              </g>
                            );
                          })}
                        </svg>
                      </div>
                    ) : (
                      <div style={{ fontSize: 12, opacity: 0.72 }}>No active image verification artifact yet.</div>
                    )}
                    <div style={{ display: 'grid', gap: 8 }}>
                      {imageVerifyResults.length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                          {imageVerifyResults.map((result: any, idx: number) => {
                            const st = String(result?.status || '').toLowerCase();
                            const active = idx === Math.min(selectedVerifyResultIndex, imageVerifyResults.length - 1);
                            const bg = st === 'match' || st === 'confirmed' ? 'rgba(42,196,119,0.2)' : st === 'mismatch' || st === 'rejected' ? 'rgba(255,107,107,0.2)' : 'rgba(212,168,63,0.2)';
                            return (
                              <button
                                key={`check-${idx}`}
                                onClick={() => setSelectedVerifyResultIndex(idx)}
                                style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: active ? bg : 'rgba(255,255,255,0.04)', border: active ? '1px solid rgba(255,255,255,0.4)' : '1px solid rgba(255,255,255,0.18)' }}
                              >
                                {String(result?.check_id || `check_${idx + 1}`)}
                              </button>
                            );
                          })}
                        </div>
                      )}
                      {selectedVerifyResult && (
                        <div style={{ fontSize: 11, opacity: 0.82, lineHeight: 1.4 }}>
                          <div>Status: {String(selectedVerifyResult.status || 'unknown')}</div>
                          <div>Observed: {String(selectedVerifyResult.observed_text || '').slice(0, 180)}</div>
                          {selectedVerifyMeta?.crop_box && (
                            <div>
                              Crop: x={Number(selectedVerifyMeta.crop_box.x) || 0}, y={Number(selectedVerifyMeta.crop_box.y) || 0}, w={Number(selectedVerifyMeta.crop_box.width) || 0}, h={Number(selectedVerifyMeta.crop_box.height) || 0}
                            </div>
                          )}
                          {selectedVerifyMeta?.zoom_factor && <div>Zoom: {String(selectedVerifyMeta.zoom_factor)}x</div>}
                        </div>
                      )}
                      <div style={{ fontSize: 11, opacity: 0.75 }}>
                        Showing current image used for verification with per-check crop overlays when available.
                      </div>
                    </div>
                  </div>
                )}

                {activeCanvasPage === 'ops' && (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
                    {readableArtifactText(selectedArtifactJson)}
                  </pre>
                )}

                {activeCanvasPage === 'wip_preview' && (
                  <div style={{ height: '100%', display: 'grid', placeItems: 'center' }}>
                    {previewPathD ? (
                      <svg viewBox="0 0 1000 1000" style={{ width: '100%', height: '100%', maxHeight: 560, borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.02)' }}>
                        <path d={previewPathD} fill="rgba(142,197,255,0.18)" stroke="#8ec5ff" strokeWidth={4} />
                      </svg>
                    ) : (
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ fontSize: 14, opacity: 0.9 }}>Constructing geometry preview…</div>
                        <div style={{ fontSize: 11, opacity: 0.7, marginTop: 6 }}>Work-in-progress view can display incomplete geometry states.</div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div style={{ position: 'absolute', top: 12, right: 12, width: 336, bottom: 78, borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(0,0,0,0.42)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: connected ? '#2ac477' : '#d4a83f' }} />
                <span style={{ fontSize: 11, opacity: 0.86 }}>Agent Intent Stream</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.68 }}>{orderedEvents.length} updates</span>
              </div>
              {isHydratingReplay && (
                <div style={{ padding: '6px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 10, opacity: 0.76 }}>
                  Replaying buffered events. Switching to live stream...
                </div>
              )}

              <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', gap: 8, alignItems: 'center' }}>
                {isRunTerminal ? (
                  <span
                    style={{
                      width: 11,
                      height: 11,
                      borderRadius: 999,
                      background: terminalStatus === 'completed' ? '#2ac477' : terminalStatus === 'failed' ? '#ff6b6b' : '#d4a83f',
                      display: 'inline-block',
                      flexShrink: 0,
                    }}
                  />
                ) : (
                  <span
                    style={{
                      width: 11,
                      height: 11,
                      borderRadius: 999,
                      border: '2px solid rgba(255,255,255,0.28)',
                      borderTopColor: '#8ec5ff',
                      display: 'inline-block',
                      animation: 'agentViewerSpin 1s linear infinite',
                      flexShrink: 0,
                    }}
                  />
                )}
                <div style={{ fontSize: 12, lineHeight: 1.35 }}>{currentStatusText}</div>
              </div>

              {terminalSummary && (
                <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11, lineHeight: 1.4, opacity: 0.9 }}>
                  <div>Status: {String(terminalSummary.status || 'unknown')}</div>
                  <div>Reason: {String(terminalSummary.reason_code || 'n/a')}</div>
                  <div>Closure State: {String(terminalSummary.closure_state || 'unknown')}</div>
                  <div>Unresolved Requirements: {unresolvedRequirementsCount}</div>
                  <div>Edits Applied: {Number(terminalSummary.edits_applied_total || 0)}</div>
                  <div>HITL Used: {terminalSummary.used_human_feedback ? 'yes' : 'no'}</div>
                </div>
              )}

              {decisionItems.length > 0 && (
                <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11, lineHeight: 1.35 }}>
                  <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 6 }}>Decision Checklist</div>
                  {decisionSummary && (
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6, opacity: 0.78 }}>
                      <span>Open: {Number(decisionSummary.blocking_open_count || 0)}</span>
                      <span>Verified: {Number(decisionSummary.verified_count || 0)}</span>
                      <span>Disputed: {Number(decisionSummary.disputed_count || 0)}</span>
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 160, overflowY: 'auto' }}>
                    {decisionItems.slice(0, 10).map((item, idx) => {
                      const state = String(item.state || 'unknown');
                      const blocking = Boolean(item.blocking);
                      const decisionKey = String(item.key || '');
                      const closure = item.closure_requirement && typeof item.closure_requirement === 'object'
                        ? (item.closure_requirement as ClosureRequirement)
                        : null;
                      const closureReason = String(closure?.block_reason || '').toLowerCase();
                      const closureReasonBg =
                        closureReason === 'ambiguity' ? 'rgba(142,197,255,0.22)' :
                        closureReason === 'contradiction' ? 'rgba(255,107,107,0.24)' :
                        closureReason === 'dependency' ? 'rgba(212,168,63,0.26)' : 'rgba(255,255,255,0.15)';
                      const stateColor =
                        state === 'verified' ? '#2ac477' :
                        state === 'disputed' ? '#ff6b6b' :
                        state === 'accepted_with_risk' ? '#d4a83f' : '#8ec5ff';
                      return (
                        <div key={`${String(item.key || idx)}`} style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '5px 6px', background: 'rgba(255,255,255,0.02)' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999, background: `${stateColor}33`, border: `1px solid ${stateColor}66` }}>
                              {state.replace(/_/g, ' ')}
                            </span>
                            <span style={{ fontSize: 11, opacity: 0.9 }}>{String(item.label || item.key || 'decision')}</span>
                            {blocking && <span style={{ fontSize: 10, opacity: 0.65 }}>(blocking)</span>}
                            {decisionKey && (
                              <button
                                onClick={() => requestDecisionReview(decisionKey)}
                                disabled={feedbackBusy || isRunTerminal}
                                style={{ marginLeft: 'auto', fontSize: 10, padding: '1px 6px', borderRadius: 999 }}
                              >
                                Review Again
                              </button>
                            )}
                          </div>
                          {item.selected_value && (
                            <div style={{ marginTop: 3, opacity: 0.82 }}>Selected: {String(item.selected_value)}</div>
                          )}
                          {Array.isArray(item.alternatives) && item.alternatives.length > 0 && (
                            <div style={{ marginTop: 2, opacity: 0.7 }}>
                              Alt: {item.alternatives.slice(0, 3).map((v) => String(v)).join(' | ')}
                            </div>
                          )}
                          {closure && (
                            <div style={{ marginTop: 5, borderTop: '1px dashed rgba(255,255,255,0.12)', paddingTop: 5 }}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                                <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999, background: closureReasonBg }}>
                                  {closureReasonLabel(closureReason)}
                                </span>
                                <span style={{ fontSize: 10, opacity: 0.68 }}>
                                  self-retrievable: {String(closure.self_retrievable || 'unknown')}
                                </span>
                              </div>
                              {closure.required_information && (
                                <div style={{ fontSize: 10, opacity: 0.86 }}>
                                  Need: {String(closure.required_information)}
                                </div>
                              )}
                              {closure.minimal_user_action && (
                                <div style={{ fontSize: 10, opacity: 0.72 }}>
                                  Action: {String(closure.minimal_user_action)}
                                </div>
                              )}
                              {closure.attempt_summary && (
                                <div style={{ fontSize: 10, opacity: 0.64 }}>
                                  Attempt: {String(closure.attempt_summary)}
                                </div>
                              )}
                              {Array.isArray(closure.evidence_refs) && closure.evidence_refs.length > 0 && (
                                <div style={{ marginTop: 2, fontSize: 10, opacity: 0.62 }}>
                                  Evidence: {closure.evidence_refs.slice(0, 3).join(', ')}
                                </div>
                              )}
                              {Array.isArray(closure.resolution_options) && closure.resolution_options.length > 0 && decisionKey && (
                                <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginTop: 5 }}>
                                  {closure.resolution_options.slice(0, 4).map((option, optionIdx) => (
                                    <button
                                      key={`${decisionKey}-opt-${optionIdx}`}
                                      onClick={() => submitDecisionResolution(decisionKey, String(option))}
                                      disabled={feedbackBusy || isRunTerminal}
                                      style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999 }}
                                    >
                                      {String(option)}
                                    </button>
                                  ))}
                                </div>
                              )}
                              {decisionKey && (
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 4, marginTop: 4 }}>
                                  <input
                                    value={String(decisionOtherByKey[decisionKey] || '')}
                                    onChange={(e) => setDecisionOtherByKey((prev) => ({ ...prev, [decisionKey]: e.target.value }))}
                                    placeholder="Other value"
                                    style={{ minWidth: 0, borderRadius: 6, border: '1px solid rgba(255,255,255,0.18)', background: 'rgba(255,255,255,0.02)', padding: '3px 6px', fontSize: 10 }}
                                  />
                                  <button
                                    onClick={() => submitDecisionResolution(decisionKey, null)}
                                    disabled={feedbackBusy || isRunTerminal || !String(decisionOtherByKey[decisionKey] || '').trim()}
                                    style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999 }}
                                  >
                                    Send Other
                                  </button>
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {upstreamCorrectionRequests.length > 0 && (
                <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11, lineHeight: 1.35 }}>
                  <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 6 }}>Upstream Correction Requests</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 130, overflowY: 'auto' }}>
                    {upstreamCorrectionRequests.slice(0, 6).map((req, idx) => (
                      <div key={`${String(req.request_id || idx)}`} style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '5px 6px', background: 'rgba(255,255,255,0.02)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontSize: 10, padding: '1px 6px', borderRadius: 999, background: req.severity === 'blocking' ? 'rgba(255,107,107,0.28)' : 'rgba(212,168,63,0.28)' }}>
                            {String(req.severity || 'caution')}
                          </span>
                          <span style={{ opacity: 0.92 }}>{String(req.reason_code || 'mapping_transcript_suspect')}</span>
                        </div>
                        <div style={{ marginTop: 3, opacity: 0.82 }}>{String(req.message || '').slice(0, 170)}</div>
                        {Array.isArray(req.decision_keys) && req.decision_keys.length > 0 && (
                          <div style={{ marginTop: 2, opacity: 0.7 }}>Keys: {req.decision_keys.slice(0, 4).join(', ')}</div>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {recentFeedbackEntries.length > 0 && (
                <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11, lineHeight: 1.35 }}>
                  <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 6 }}>Recent Feedback</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 120, overflowY: 'auto' }}>
                    {recentFeedbackEntries.map((entry, idx) => (
                      <div key={`${entry.submitted_at_epoch_seconds}-${idx}`} style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '5px 6px', background: 'rgba(255,255,255,0.02)' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span style={{ fontSize: 10, opacity: 0.62 }}>
                            {new Date((Number(entry.submitted_at_epoch_seconds) || 0) * 1000).toLocaleTimeString()}
                          </span>
                          {entry.choice && <span style={{ opacity: 0.9 }}>{String(entry.choice)}</span>}
                          {entry.prompt_id && <span style={{ fontSize: 10, opacity: 0.58 }}>{String(entry.prompt_id)}</span>}
                          <button
                            onClick={() => resendFeedbackEntry(entry)}
                            disabled={feedbackBusy || isRunTerminal}
                            style={{ marginLeft: 'auto', fontSize: 10, padding: '1px 6px', borderRadius: 999 }}
                          >
                            Resend
                          </button>
                        </div>
                        {entry.note && <div style={{ marginTop: 2, opacity: 0.72 }}>{String(entry.note).slice(0, 160)}</div>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {detailEvent && (
                <div style={{ padding: '0 12px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <EventDetailBlock evt={detailEvent} />
                </div>
              )}

              <div style={{ padding: '10px 12px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {floatingHistory.map((item) => (
                  <div
                    key={`${item.idx}:${item.iteration ?? 'na'}`}
                    style={{
                      fontSize: item.isTicker ? 10 : item.isCurrent ? 12 : 11,
                      opacity: item.isTicker ? 0.58 : item.isCurrent ? 0.96 : 0.78,
                      lineHeight: 1.35,
                    }}
                  >
                    {item.isReplay ? 'R ' : item.isTicker ? '∙ ' : item.isCurrent ? '• ' : '· '} {item.text}
                  </div>
                ))}
              </div>
            </div>

            <div style={{ position: 'absolute', left: 12, right: 12, bottom: 12, borderRadius: 12, border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(0,0,0,0.58)', padding: 10 }}>
              {activeFeedbackPrompt && (
                <div
                  style={{
                    marginBottom: 8,
                    padding: '10px 12px',
                    borderRadius: 10,
                    border: activeFeedbackPrompt.blocking
                      ? '1px solid rgba(255, 171, 64, 0.85)'
                      : '1px solid rgba(255,255,255,0.16)',
                    background: activeFeedbackPrompt.blocking
                      ? 'linear-gradient(180deg, rgba(255,171,64,0.14), rgba(255,171,64,0.05))'
                      : 'rgba(255,255,255,0.04)',
                    boxShadow:
                      activeFeedbackPrompt.blocking && !activePromptSatisfied
                        ? '0 0 0 1px rgba(255,171,64,0.22), 0 0 14px rgba(255,171,64,0.24)'
                        : 'none',
                    animation:
                      activeFeedbackPrompt.blocking && !activePromptSatisfied
                        ? 'agentViewerPulse 1.4s ease-in-out infinite'
                        : 'none',
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 600 }}>{activeFeedbackPrompt.line1}</div>
                  {!!activeFeedbackPrompt.line2 && <div style={{ fontSize: 11, opacity: 0.8, marginTop: 2 }}>{activeFeedbackPrompt.line2}</div>}
                  {!activeFeedbackPrompt.blocking && (
                    <div style={{ fontSize: 10, opacity: 0.7, marginTop: 3 }}>
                      Non-blocking. The loop continues while this feedback is pending.
                    </div>
                  )}
                  <div style={{ fontSize: 10, opacity: 0.64, marginTop: 3 }}>prompt_id: {activeFeedbackPrompt.promptId}</div>
                </div>
              )}

              {!activeFeedbackPrompt && promptReceipt && (
                <div style={{ marginBottom: 8, padding: '7px 10px', borderRadius: 8, border: '1px solid rgba(42,196,119,0.45)', background: 'rgba(42,196,119,0.14)', fontSize: 11 }}>
                  {promptReceipt}
                </div>
              )}

              {activeFeedbackPrompt?.choices?.length ? (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                  {activeFeedbackPrompt.choices.map((choice) => (
                    <button key={choice} onClick={() => submitFeedback(choice)} disabled={feedbackBusy || activePromptSatisfied || isRunTerminal} style={{ fontSize: 11, borderRadius: 999, padding: '4px 8px' }}>
                      {choice}
                    </button>
                  ))}
                </div>
              ) : null}

              <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', gap: 8, alignItems: 'end' }}>
                <textarea
                  value={feedbackNote}
                  onChange={(e) => setFeedbackNote(e.target.value)}
                  rows={2}
                  placeholder="Send guidance to the agent..."
                  style={{ width: '100%', resize: 'vertical', borderRadius: 8, border: '1px solid rgba(255,255,255,0.18)', background: 'rgba(255,255,255,0.02)', padding: 8, fontSize: 12 }}
                />
                <button onClick={() => submitFeedback()} disabled={feedbackBusy || activePromptSatisfied || isRunTerminal} style={{ height: 34, borderRadius: 8, padding: '0 10px', fontSize: 12 }}>
                  {feedbackBusy ? 'Sending…' : 'Send'}
                </button>
              </div>

              {feedbackError && <div style={{ marginTop: 6, fontSize: 11, color: '#ff9aa0' }}>{feedbackError}</div>}
              {activePromptSatisfied && <div style={{ marginTop: 6, fontSize: 11, color: '#8ee5b0' }}>Prompt response received.</div>}
            </div>

            <style>{`
              @keyframes agentViewerSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
              @keyframes agentViewerPulse {
                0% { box-shadow: 0 0 0 1px rgba(255,171,64,0.16), 0 0 8px rgba(255,171,64,0.14); }
                50% { box-shadow: 0 0 0 1px rgba(255,171,64,0.3), 0 0 20px rgba(255,171,64,0.32); }
                100% { box-shadow: 0 0 0 1px rgba(255,171,64,0.16), 0 0 8px rgba(255,171,64,0.14); }
              }
            `}</style>
          </div>
        )}
      </div>
    </div>
  );
};





