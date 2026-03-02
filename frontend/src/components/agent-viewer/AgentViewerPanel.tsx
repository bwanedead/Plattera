import React from 'react';
import {
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
  if (evt.event_type === 'human_feedback_needed') return 'Next, I need your decision before proceeding.';
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
  const [canvasMode, setCanvasMode] = React.useState<CanvasMode>('transcription');
  const [selectedDraftIndex, setSelectedDraftIndex] = React.useState(0);
  const [theme, setTheme] = React.useState<ViewerTheme>('void');
  const [lensing, setLensing] = React.useState<{ x: number; y: number; active: boolean }>({ x: 50, y: 50, active: false });
  const [selectedArtifactRef, setSelectedArtifactRef] = React.useState<string | null>(null);
  const [selectedArtifactJson, setSelectedArtifactJson] = React.useState<any>(null);
  const [artifactError, setArtifactError] = React.useState<string | null>(null);
  const [loadingArtifact, setLoadingArtifact] = React.useState(false);

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
    const unsubscribe = subscribeAgentViewerEvents(
      activeLoopKind,
      activeRunId,
      (event) => {
        setConnected(true);
        setEvents((prev) => [event, ...prev].slice(0, 250));
      },
      () => setConnected(false),
    );
    return () => unsubscribe();
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
  const currentEvent = doneEvent || orderedEvents[0] || null;
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

  const activeFeedbackPrompt = React.useMemo(() => {
    if (isRunTerminal) return null;
    for (const evt of orderedEvents) {
      if (evt.event_type !== 'human_feedback_needed') continue;
      const promptId = typeof evt.payload?.prompt_id === 'string' ? evt.payload.prompt_id : '';
      if (!promptId) continue;
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
  }, [orderedEvents, isRunTerminal]);

  const activePromptSatisfied = React.useMemo(() => {
    if (!activeFeedbackPrompt?.promptId) return false;
    return feedbackEntries.some((entry) => String(entry.prompt_id || '') === activeFeedbackPrompt.promptId);
  }, [activeFeedbackPrompt, feedbackEntries]);

  React.useEffect(() => {
    if (canvasMode !== 'agent') return;
    if (!orderedEvents.length) return;
    const eventsWithRefs = orderedEvents.filter(
      (evt) => evt && evt.artifact_refs && Object.keys(evt.artifact_refs).length > 0,
    );
    if (!eventsWithRefs.length) return;
    const phaseRefKeys: Record<string, string[]> = {
      audit: ['tx_validator_report_ref'],
      audit_result: ['tx_validator_report_ref'],
      open_spans: ['tx_open_spans_ref'],
      open_spans_result: ['tx_open_spans_ref'],
      image_verify: ['tx_image_verify_ref'],
      image_verify_result: ['tx_image_verify_ref'],
      plan: ['tx_edit_plan_ref'],
      plan_result: ['tx_edit_plan_ref'],
      apply: ['tx_edited_transcript_ref', 'tx_apply_report_ref'],
      apply_result: ['tx_edited_transcript_ref', 'tx_apply_report_ref'],
      promote: ['tx_mapping_pointer_ref'],
    };
    let bestRef: string | null = null;
    for (const evt of eventsWithRefs) {
      const refs = evt.artifact_refs || {};
      const phase = String(evt.payload?.phase || evt.status?.stage || '').toLowerCase();
      const preferredKeys = phaseRefKeys[phase] || [];
      for (const key of preferredKeys) {
        const ref = refs[key];
        if (ref?.artifact_path) {
          bestRef = ref.artifact_path;
          break;
        }
      }
      if (bestRef) break;
      for (const key of ['tx_edited_transcript_ref', 'tx_source_transcript_ref', 'tx_validator_report_ref', 'ir_ref']) {
        const ref = refs[key];
        if (ref?.artifact_path) {
          bestRef = ref.artifact_path;
          break;
        }
      }
      if (bestRef) break;
    }
    if (bestRef && bestRef !== selectedArtifactRef) {
      setSelectedArtifactRef(bestRef);
    }
  }, [canvasMode, orderedEvents, selectedArtifactRef]);

  React.useEffect(() => {
    if (!selectedArtifactRef) return;
    let cancelled = false;
    setLoadingArtifact(true);
    setArtifactError(null);
    (async () => {
      try {
        const payload = await getAgentViewerArtifactJson(selectedArtifactRef);
        if (!cancelled) setSelectedArtifactJson(payload?.json ?? null);
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
  }, [selectedArtifactRef]);

  const submitFeedback = React.useCallback(async (choice?: string) => {
    if (!activeLoopKind || !activeRunId) return;
    setFeedbackBusy(true);
    setFeedbackError(null);
    try {
      const response = await submitAgentViewerFeedback(activeLoopKind, activeRunId, {
        prompt_id: activeFeedbackPrompt?.promptId || null,
        choice: choice || null,
        note: feedbackNote.trim() || null,
        metadata: {
          canvas_mode: canvasMode,
          event_count: orderedEvents.length,
        },
      });
      setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 40));
      setFeedbackNote('');
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : 'Failed to submit feedback');
    } finally {
      setFeedbackBusy(false);
    }
  }, [activeLoopKind, activeRunId, activeFeedbackPrompt, feedbackNote, canvasMode, orderedEvents.length]);

  const readableCanvasText = React.useMemo(() => readableArtifactText(selectedArtifactJson), [selectedArtifactJson]);

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
              {currentEvent && (
                <div style={{ padding: '6px 14px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
                  <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: 'rgba(142,197,255,0.15)', border: '1px solid rgba(142,197,255,0.25)' }}>
                    {String(currentEvent.payload?.phase || currentEvent.status?.stage || 'idle').replace(/_/g, ' ')}
                  </span>
                  {typeof currentEvent.iteration === 'number' && (
                    <span style={{ fontSize: 10, opacity: 0.6 }}>iter {currentEvent.iteration}</span>
                  )}
                </div>
              )}
              <div style={{ flex: 1, overflow: 'auto', padding: 14 }}>
                {loadingArtifact && <div style={{ fontSize: 12, opacity: 0.86 }}>Loading latest artifact…</div>}
                {artifactError && <div style={{ fontSize: 12, color: '#ff9aa0' }}>{artifactError}</div>}
                {!loadingArtifact && !artifactError && !selectedArtifactJson && (
                  <div style={{ fontSize: 12, opacity: 0.72 }}>No artifact loaded yet. Waiting for agent outputs…</div>
                )}
                {!loadingArtifact && !artifactError && selectedArtifactJson && (
                  <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
                    {readableCanvasText}
                  </pre>
                )}
              </div>
            </div>

            <div style={{ position: 'absolute', top: 12, right: 12, width: 336, bottom: 78, borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(0,0,0,0.42)', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div style={{ padding: '10px 12px', borderBottom: '1px solid rgba(255,255,255,0.08)', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span style={{ width: 8, height: 8, borderRadius: 999, background: connected ? '#2ac477' : '#d4a83f' }} />
                <span style={{ fontSize: 11, opacity: 0.86 }}>Agent Intent Stream</span>
                <span style={{ marginLeft: 'auto', fontSize: 10, opacity: 0.68 }}>{orderedEvents.length} updates</span>
              </div>

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
                  <div>Edits Applied: {Number(terminalSummary.edits_applied_total || 0)}</div>
                  <div>HITL Used: {terminalSummary.used_human_feedback ? 'yes' : 'no'}</div>
                </div>
              )}

              {detailEvent && (
                <div style={{ padding: '0 12px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <EventDetailBlock evt={detailEvent} />
                </div>
              )}

              <div style={{ padding: '10px 12px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8 }}>
                {floatingHistory.map((item) => (
                  <div key={`${item.idx}:${item.iteration ?? 'na'}`} style={{ fontSize: item.isCurrent ? 12 : 11, opacity: item.isCurrent ? 0.96 : 0.78, lineHeight: 1.35 }}>
                    {item.isCurrent ? '• ' : '· '} {item.text}
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
                  <div style={{ fontSize: 10, opacity: 0.64, marginTop: 3 }}>prompt_id: {activeFeedbackPrompt.promptId}</div>
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
