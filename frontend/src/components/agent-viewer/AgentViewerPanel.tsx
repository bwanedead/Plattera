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
  onClose: () => void;
}

export const AgentViewerPanel: React.FC<AgentViewerPanelProps> = ({
  isOpen,
  loopKind,
  runId,
  onClose,
}) => {
  const [events, setEvents] = React.useState<AgentViewerEvent[]>([]);
  const [connected, setConnected] = React.useState(false);
  const arrivalSeqRef = React.useRef(0);
  const [expandedGroups, setExpandedGroups] = React.useState<Record<string, boolean>>({});
  const [focusedGroupKey, setFocusedGroupKey] = React.useState<string | null>(null);
  const [selectedArtifactRef, setSelectedArtifactRef] = React.useState<string | null>(null);
  const [selectedArtifactJson, setSelectedArtifactJson] = React.useState<any>(null);
  const [artifactError, setArtifactError] = React.useState<string | null>(null);
  const [loadingArtifact, setLoadingArtifact] = React.useState(false);
  const [activeArtifactTab, setActiveArtifactTab] = React.useState<'selected' | 'pinned' | 'latest'>('selected');
  const [pinnedArtifacts, setPinnedArtifacts] = React.useState<Array<{
    artifactRef: string;
    label: string;
    pinnedAtSeq: number;
  }>>([]);
  const [feedbackEntries, setFeedbackEntries] = React.useState<AgentViewerFeedbackEntry[]>([]);
  const [feedbackNote, setFeedbackNote] = React.useState('');
  const [feedbackBusy, setFeedbackBusy] = React.useState(false);
  const [feedbackError, setFeedbackError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!isOpen || !loopKind || !runId) return;
    setEvents([]);
    setConnected(false);
    arrivalSeqRef.current = 0;
    setExpandedGroups({});
    setFocusedGroupKey(null);
    setPinnedArtifacts([]);
    setActiveArtifactTab('selected');
    setFeedbackEntries([]);
    setFeedbackNote('');
    setFeedbackError(null);
    const unsubscribe = subscribeAgentViewerEvents(
      loopKind,
      runId,
      (event) => {
        setConnected(true);
        arrivalSeqRef.current += 1;
        setEvents((prev) => {
          const tagged = { ...event, payload: { ...(event.payload || {}), _arrival_order: arrivalSeqRef.current } };
          return [tagged, ...prev].slice(0, 200);
        });
      },
      () => setConnected(false),
    );
    return () => unsubscribe();
  }, [isOpen, loopKind, runId]);

  React.useEffect(() => {
    if (!isOpen || !loopKind || !runId) return;
    let cancelled = false;
    (async () => {
      try {
        const feedback = await getAgentViewerFeedback(loopKind, runId);
        if (cancelled) return;
        setFeedbackEntries(Array.isArray(feedback.entries) ? feedback.entries : []);
      } catch {
        if (!cancelled) setFeedbackEntries([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [isOpen, loopKind, runId]);

  const openArtifact = React.useCallback(async (artifactRef: string) => {
    setSelectedArtifactRef(artifactRef);
    setLoadingArtifact(true);
    setArtifactError(null);
    setActiveArtifactTab('selected');
    try {
      const payload = await getAgentViewerArtifactJson(artifactRef);
      setSelectedArtifactJson(payload?.json ?? null);
    } catch (error) {
      setSelectedArtifactJson(null);
      setArtifactError(error instanceof Error ? error.message : 'Failed to open artifact');
    } finally {
      setLoadingArtifact(false);
    }
  }, []);

  const pinArtifact = React.useCallback((artifactRef: string, label: string) => {
    if (!artifactRef) return;
    setPinnedArtifacts((prev) => {
      const next = prev.filter((item) => item.artifactRef !== artifactRef);
      next.unshift({ artifactRef, label, pinnedAtSeq: arrivalSeqRef.current });
      return next.slice(0, 20);
    });
    setActiveArtifactTab('pinned');
  }, []);

  const openBestArtifactForGroup = React.useCallback((groupEvents: AgentViewerEvent[]) => {
    for (const evt of groupEvents) {
      const refs = evt.artifact_refs || {};
      const firstRef = Object.values(refs)[0];
      if (firstRef?.artifact_path) {
        void openArtifact(firstRef.artifact_path);
        return;
      }
    }
  }, [openArtifact]);

  const orderedEvents = React.useMemo(() => {
    const withArrival = events.map((evt, index) => ({
      evt,
      idx: index,
      seq: typeof evt.seq === 'number' ? evt.seq : null,
      ts: typeof evt.timestamp_epoch_seconds === 'number' ? evt.timestamp_epoch_seconds : null,
      arrival: typeof evt.payload?._arrival_order === 'number'
        ? evt.payload._arrival_order
        : (events.length - index),
    }));
    withArrival.sort((a, b) => {
      if (a.seq != null && b.seq != null && a.seq !== b.seq) return b.seq - a.seq;
      if (a.ts != null && b.ts != null && a.ts !== b.ts) return b.ts - a.ts;
      return b.arrival - a.arrival;
    });
    return withArrival.map((x) => x.evt);
  }, [events]);

  type Group = {
    key: string;
    kind: 'iteration' | 'ungrouped';
    iteration: number | null;
    events: AgentViewerEvent[];
    latestStage: string;
  };

  const groups = React.useMemo<Group[]>(() => {
    const byKey = new Map<string, Group>();
    for (const evt of orderedEvents) {
      const iter = typeof evt.iteration === 'number' ? evt.iteration : null;
      const key = iter != null ? `iter:${iter}` : `ungrouped:${evt.event_type || 'status'}`;
      const existing = byKey.get(key);
      if (!existing) {
        byKey.set(key, {
          key,
          kind: iter != null ? 'iteration' : 'ungrouped',
          iteration: iter,
          events: [evt],
          latestStage: String(evt.status?.stage || evt.event_type || 'event'),
        });
      } else {
        existing.events.push(evt);
      }
    }
    const out = Array.from(byKey.values());
    out.sort((a, b) => {
      const ai = a.iteration;
      const bi = b.iteration;
      if (ai != null && bi != null && ai !== bi) return bi - ai;
      if (ai != null) return -1;
      if (bi != null) return 1;
      return a.key.localeCompare(b.key);
    });
    for (const g of out) {
      g.events.sort((a, b) => {
        const as = typeof a.seq === 'number' ? a.seq : null;
        const bs = typeof b.seq === 'number' ? b.seq : null;
        if (as != null && bs != null && as !== bs) return bs - as;
        const at = typeof a.timestamp_epoch_seconds === 'number' ? a.timestamp_epoch_seconds : null;
        const bt = typeof b.timestamp_epoch_seconds === 'number' ? b.timestamp_epoch_seconds : null;
        if (at != null && bt != null && at !== bt) return bt - at;
        return 0;
      });
      g.latestStage = String(g.events[0]?.status?.stage || g.events[0]?.event_type || 'event');
    }
    return out;
  }, [orderedEvents]);

  React.useEffect(() => {
    const maxIteration = groups
      .map((g) => g.iteration)
      .filter((v): v is number => typeof v === 'number')
      .sort((a, b) => b - a)[0];
    if (typeof maxIteration !== 'number') return;
    const key = `iter:${maxIteration}`;
    setExpandedGroups((prev) => ({ ...prev, [key]: true }));
    if (!focusedGroupKey) {
      setFocusedGroupKey(key);
    }
  }, [groups, focusedGroupKey]);

  const latestRefs = React.useMemo(() => {
    const refs: Array<{ label: string; artifactRef: string }> = [];
    for (const evt of orderedEvents) {
      const entries = Object.entries(evt.artifact_refs || {});
      if (entries.length === 0) continue;
      for (const [label, value] of entries) {
        if (value?.artifact_path) refs.push({ label, artifactRef: value.artifact_path });
      }
      if (refs.length > 0) break;
    }
    return refs.slice(0, 8);
  }, [orderedEvents]);

  const toggleGroup = React.useCallback((key: string, groupEvents: AgentViewerEvent[]) => {
    setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }));
    setFocusedGroupKey(key);
    openBestArtifactForGroup(groupEvents);
  }, [openBestArtifactForGroup]);

  const focusedGroupEvents = React.useMemo(() => {
    const key = focusedGroupKey;
    if (!key) return [] as AgentViewerEvent[];
    const group = groups.find((g) => g.key === key);
    return group?.events || [];
  }, [groups, focusedGroupKey]);

  const feedbackChoices = React.useMemo(() => {
    const latestPromptEvent = focusedGroupEvents.find((evt) => evt.event_type === 'human_feedback_needed');
    const promptChoices = Array.isArray(latestPromptEvent?.payload?.choices)
      ? latestPromptEvent?.payload?.choices
      : [];
    const options: string[] = promptChoices.length > 0 ? [...promptChoices] : ['Approve promotion', 'Needs more edits'];
    for (const evt of focusedGroupEvents) {
      const payload = evt.payload || {};
      const checks = Array.isArray(payload.image_verification?.checks) ? payload.image_verification.checks : [];
      for (const c of checks) {
        if (!c || typeof c !== 'object') continue;
        const expected = typeof c.expected_text === 'string' ? c.expected_text.trim() : '';
        const observed = typeof c.observed_text === 'string' ? c.observed_text.trim() : '';
        if (expected && expected.length <= 60) options.push(expected);
        if (observed && observed.length <= 60) options.push(observed);
      }
      const reasonCode = typeof payload.reason_code === 'string' ? payload.reason_code : '';
      if (/range/i.test(reasonCode)) {
        options.push('Range 74');
        options.push('Range 75');
      }
    }
    const unique = Array.from(new Set(options.map((o) => o.trim()).filter(Boolean)));
    return unique.slice(0, 8);
  }, [focusedGroupEvents]);

  const activeFeedbackPrompt = React.useMemo(() => {
    for (const evt of focusedGroupEvents) {
      if (evt.event_type !== 'human_feedback_needed') continue;
      const promptId = typeof evt.payload?.prompt_id === 'string' ? evt.payload.prompt_id : '';
      if (!promptId) continue;
      return {
        promptId,
        blocking: Boolean(evt.payload?.blocking),
        line1: evt.status?.line1 || 'Human feedback needed',
        line2: evt.status?.line2 || '',
      };
    }
    return null;
  }, [focusedGroupEvents]);

  const activePromptSatisfied = React.useMemo(() => {
    if (!activeFeedbackPrompt?.promptId) return false;
    return feedbackEntries.some((entry) => String(entry.prompt_id || '') === activeFeedbackPrompt.promptId);
  }, [activeFeedbackPrompt, feedbackEntries]);

  const submitFeedback = React.useCallback(async (choice?: string) => {
    if (!loopKind || !runId) return;
    setFeedbackBusy(true);
    setFeedbackError(null);
    try {
      const response = await submitAgentViewerFeedback(loopKind, runId, {
        prompt_id: activeFeedbackPrompt?.promptId || null,
        choice: choice || null,
        note: feedbackNote.trim() || null,
        metadata: {
          focused_group: focusedGroupKey,
          event_count: focusedGroupEvents.length,
        },
      });
      setFeedbackEntries((prev) => [response.entry, ...prev].slice(0, 30));
      setFeedbackNote('');
    } catch (error) {
      setFeedbackError(error instanceof Error ? error.message : 'Failed to submit feedback');
    } finally {
      setFeedbackBusy(false);
    }
  }, [loopKind, runId, activeFeedbackPrompt, feedbackNote, focusedGroupKey, focusedGroupEvents.length]);

  const renderEventCard = React.useCallback((evt: AgentViewerEvent) => {
    const refs = evt.artifact_refs || {};
    const refEntries = Object.entries(refs);
    const stage = String(evt.status?.stage || '').toLowerCase();
    const isDone = evt.event_type === 'done';
    const isRefusal = stage.includes('refus') || String(evt.payload?.reason_code || '').toLowerCase().includes('refus');
    const border = isDone
      ? '1px solid rgba(67, 208, 135, 0.42)'
      : isRefusal
      ? '1px solid rgba(255, 164, 92, 0.46)'
      : '1px solid rgba(255,255,255,0.08)';
    const background = isDone
      ? 'rgba(67, 208, 135, 0.08)'
      : isRefusal
      ? 'rgba(255,164,92,0.08)'
      : 'rgba(255,255,255,0.02)';
    return (
      <div
        key={`${evt.seq ?? 'na'}-${evt.timestamp_epoch_seconds ?? 'na'}-${evt.event_type}`}
        style={{ border, borderRadius: 8, padding: 8, background }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, marginBottom: 3 }}>
          <span style={{ fontSize: 10, opacity: 0.75 }}>{evt.event_type}</span>
          <span style={{ fontSize: 10, opacity: 0.7 }}>iter {evt.iteration ?? '-'}</span>
        </div>
        <div style={{ fontSize: 12, fontWeight: 600 }}>{evt.status?.line1 || 'Agent update'}</div>
        {evt.status?.line2 && <div style={{ fontSize: 11, opacity: 0.82, marginTop: 2 }}>{evt.status.line2}</div>}
        {refEntries.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4, marginTop: 6 }}>
            {refEntries.slice(0, 6).map(([key, value]) => (
              <React.Fragment key={key}>
                <button
                  onClick={() => openArtifact(value.artifact_path)}
                  style={{
                    fontSize: 10,
                    padding: '2px 6px',
                    borderRadius: 999,
                    border: '1px solid rgba(131,191,255,0.45)',
                    background: 'rgba(131,191,255,0.12)',
                  }}
                  title={value.artifact_path}
                >
                  {key}
                </button>
                <button
                  onClick={() => pinArtifact(value.artifact_path, key)}
                  style={{
                    fontSize: 10,
                    padding: '2px 6px',
                    borderRadius: 999,
                    border: '1px solid rgba(255,255,255,0.28)',
                    background: 'rgba(255,255,255,0.08)',
                  }}
                  title="Pin artifact"
                >
                  Pin
                </button>
              </React.Fragment>
            ))}
          </div>
        )}
      </div>
    );
  }, [openArtifact, pinArtifact]);

  if (!isOpen || !loopKind || !runId) return null;

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 2300,
        background: 'rgba(0,0,0,0.58)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 14,
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: 'min(1500px, 97vw)',
          height: 'min(920px, 95vh)',
          background: '#0b1018',
          border: '1px solid rgba(255,255,255,0.16)',
          borderRadius: 12,
          overflow: 'hidden',
          display: 'grid',
          gridTemplateRows: '48px 1fr',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '0 12px',
            borderBottom: '1px solid rgba(255,255,255,0.08)',
            background: '#0f1724',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <strong style={{ fontSize: 13 }}>Agent Viewer</strong>
            <span style={{ fontSize: 11, opacity: 0.8 }}>{loopKind}</span>
            <span style={{ fontSize: 11, opacity: 0.72 }}>{runId}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: 999, background: connected ? '#2ac477' : '#d4a83f' }} />
            <span style={{ fontSize: 11, opacity: 0.82 }}>{connected ? 'Live' : 'Disconnected'}</span>
            <button onClick={onClose}>Close</button>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '380px 1fr', minHeight: 0 }}>
          <div
            style={{
              borderRight: '1px solid rgba(255,255,255,0.08)',
              overflowY: 'auto',
              padding: 10,
              display: 'flex',
              flexDirection: 'column',
              gap: 8,
            }}
          >
            {groups.length === 0 && (
              <div style={{ fontSize: 12, opacity: 0.72, padding: 6 }}>Waiting for events...</div>
            )}
            {groups.map((group) => {
              const expanded = expandedGroups[group.key] ?? false;
              const isFocused = focusedGroupKey === group.key;
              return (
                <div
                  key={group.key}
                  style={{
                    border: isFocused ? '1px solid rgba(131,191,255,0.42)' : '1px solid rgba(255,255,255,0.08)',
                    borderRadius: 8,
                    background: 'rgba(255,255,255,0.015)',
                  }}
                >
                  <button
                    onClick={() => toggleGroup(group.key, group.events)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      border: 'none',
                      background: 'transparent',
                      color: 'inherit',
                      padding: '8px 10px',
                      cursor: 'pointer',
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'center',
                      gap: 8,
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                      <div style={{ fontSize: 12, fontWeight: 700 }}>
                        {group.kind === 'iteration' ? `Iteration ${group.iteration}` : 'Ungrouped / Lifecycle'}
                      </div>
                      <div style={{ fontSize: 10, opacity: 0.72 }}>
                        {group.events.length} events • latest stage={group.latestStage}
                      </div>
                    </div>
                    <div style={{ fontSize: 14, opacity: 0.78 }}>{expanded ? '▾' : '▸'}</div>
                  </button>
                  {expanded && (
                    <div style={{ padding: '0 8px 8px 8px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {group.events.map((evt) => renderEventCard(evt))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
          <div style={{ minHeight: 0, overflow: 'auto', padding: 10 }}>
            <div
              style={{
                marginBottom: 10,
                padding: 10,
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.02)',
              }}
            >
              <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 6 }}>Human Feedback</div>
              {activeFeedbackPrompt && (
                <div
                  style={{
                    marginBottom: 8,
                    padding: 8,
                    borderRadius: 6,
                    border: activeFeedbackPrompt.blocking
                      ? '1px solid rgba(255,170,92,0.55)'
                      : '1px solid rgba(255,255,255,0.18)',
                    background: activeFeedbackPrompt.blocking
                      ? 'rgba(255,170,92,0.1)'
                      : 'rgba(255,255,255,0.03)',
                  }}
                >
                  <div style={{ fontSize: 12, fontWeight: 700 }}>{activeFeedbackPrompt.line1}</div>
                  {activeFeedbackPrompt.line2 && (
                    <div style={{ fontSize: 11, opacity: 0.82, marginTop: 2 }}>{activeFeedbackPrompt.line2}</div>
                  )}
                  {activePromptSatisfied && (
                    <div style={{ fontSize: 11, marginTop: 4, color: '#8ee5b0' }}>
                      Prompt response received.
                    </div>
                  )}
                  <div style={{ fontSize: 10, opacity: 0.7, marginTop: 3 }}>
                    prompt_id: {activeFeedbackPrompt.promptId}
                  </div>
                </div>
              )}
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                {feedbackChoices.map((choice) => (
                  <button
                    key={choice}
                    onClick={() => submitFeedback(choice)}
                    disabled={feedbackBusy || !activeFeedbackPrompt || activePromptSatisfied}
                    style={{
                      fontSize: 11,
                      padding: '4px 8px',
                      borderRadius: 999,
                      border: '1px solid rgba(255,255,255,0.2)',
                      background: 'rgba(255,255,255,0.04)',
                    }}
                  >
                    {choice}
                  </button>
                ))}
              </div>
              <textarea
                value={feedbackNote}
                onChange={(e) => setFeedbackNote(e.target.value)}
                placeholder="Add nuance for the agent (optional)"
                rows={3}
                style={{
                  width: '100%',
                  resize: 'vertical',
                  fontSize: 11,
                  borderRadius: 6,
                  border: '1px solid rgba(255,255,255,0.18)',
                  background: 'rgba(255,255,255,0.03)',
                  color: 'inherit',
                  padding: 8,
                }}
              />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 6 }}>
                <button onClick={() => submitFeedback()} disabled={feedbackBusy || activePromptSatisfied}>
                  {feedbackBusy ? 'Submitting...' : 'Submit note'}
                </button>
                {feedbackError && <span style={{ fontSize: 11, color: '#ff9aa0' }}>{feedbackError}</span>}
              </div>
              {feedbackEntries.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 11, opacity: 0.82 }}>
                  Latest: {feedbackEntries[0]?.choice || feedbackEntries[0]?.note || 'feedback'}
                </div>
              )}
            </div>
            <div style={{ display: 'flex', gap: 6, marginBottom: 8 }}>
              {(['selected', 'pinned', 'latest'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() => setActiveArtifactTab(tab)}
                  style={{
                    fontSize: 11,
                    padding: '4px 8px',
                    borderRadius: 999,
                    border: activeArtifactTab === tab
                      ? '1px solid rgba(131,191,255,0.58)'
                      : '1px solid rgba(255,255,255,0.18)',
                    background: activeArtifactTab === tab
                      ? 'rgba(131,191,255,0.12)'
                      : 'rgba(255,255,255,0.03)',
                  }}
                >
                  {tab === 'selected' ? 'Selected' : tab === 'pinned' ? `Pinned (${pinnedArtifacts.length})` : 'Latest refs'}
                </button>
              ))}
            </div>
            {activeArtifactTab === 'selected' && (
              <div style={{ fontSize: 12, opacity: 0.78, marginBottom: 6 }}>
                {selectedArtifactRef ? `Artifact: ${selectedArtifactRef}` : 'Select an artifact from the timeline'}
              </div>
            )}
            {activeArtifactTab === 'pinned' && (
              <div style={{ marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {pinnedArtifacts.length === 0 && (
                  <div style={{ fontSize: 12, opacity: 0.72 }}>No pinned artifacts yet.</div>
                )}
                {pinnedArtifacts.map((item) => (
                  <div key={item.artifactRef} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button onClick={() => openArtifact(item.artifactRef)}>{item.label}</button>
                    <span style={{ fontSize: 10, opacity: 0.7 }}>{item.artifactRef}</span>
                  </div>
                ))}
              </div>
            )}
            {activeArtifactTab === 'latest' && (
              <div style={{ marginBottom: 10, display: 'flex', flexDirection: 'column', gap: 6 }}>
                {latestRefs.length === 0 && (
                  <div style={{ fontSize: 12, opacity: 0.72 }}>No artifact refs in latest events.</div>
                )}
                {latestRefs.map((item) => (
                  <div key={`${item.label}:${item.artifactRef}`} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <button onClick={() => openArtifact(item.artifactRef)}>{item.label}</button>
                    <button onClick={() => pinArtifact(item.artifactRef, item.label)}>Pin</button>
                  </div>
                ))}
              </div>
            )}
            {loadingArtifact && <div style={{ fontSize: 12 }}>Loading artifact…</div>}
            {artifactError && <div style={{ fontSize: 12, color: '#ff9aa0' }}>{artifactError}</div>}
            {!loadingArtifact && !artifactError && selectedArtifactJson && (
              <pre
                style={{
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                  fontSize: 11,
                  lineHeight: 1.35,
                  margin: 0,
                  padding: 10,
                  borderRadius: 8,
                  border: '1px solid rgba(255,255,255,0.08)',
                  background: 'rgba(255,255,255,0.02)',
                }}
              >
                {JSON.stringify(selectedArtifactJson, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
