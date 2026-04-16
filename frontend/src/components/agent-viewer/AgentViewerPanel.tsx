import React from 'react';
import { AgentSidebar } from './AgentSidebar';
import { AgentCanvasPane } from './AgentCanvasPane';
import { FeedbackComposer } from './FeedbackComposer';
import { AgentViewerHeader } from './AgentViewerHeader';
import { TranscriptionCanvasPane } from './TranscriptionCanvasPane';
import { useAgentViewerStream } from './hooks/useAgentViewerStream';
import { useAgentViewerFeedback } from './hooks/useAgentViewerFeedback';
import { useAgentViewerArtifacts } from './hooks/useAgentViewerArtifacts';
import {
  buildLaneChips,
  collectUpstreamCorrectionRequests,
  extractDecisionLedger,
  summarizeEventForesight,
} from './agentViewerUtils';
import type { AgentViewerPanelProps, CanvasMode, DecisionLedgerItem, ViewerTheme } from './types';

export const AgentViewerPanel: React.FC<AgentViewerPanelProps> = ({
  isOpen,
  loopKind,
  runId,
  sessionKey,
  transcriptionDrafts = [],
  isTranscribing = false,
  onClose,
}) => {
  const [canvasMode, setCanvasMode] = React.useState<CanvasMode>('transcription');
  const [selectedDraftIndex, setSelectedDraftIndex] = React.useState(0);
  const [theme, setTheme] = React.useState<ViewerTheme>('void');
  const [lensing, setLensing] = React.useState<{ x: number; y: number; active: boolean }>({ x: 50, y: 50, active: false });
  const lastPromptRenderLogRef = React.useRef<string>('');

  const activeLoopKind = loopKind ?? null;
  const activeRunId = typeof runId === 'string' && runId.trim() ? runId : null;
  const hasActiveRun = Boolean(activeLoopKind && activeRunId);
  const { events, setEvents, connected, setConnected, isHydratingReplay } = useAgentViewerStream({
    isOpen,
    activeLoopKind,
    activeRunId,
  });

  React.useEffect(() => {
    if (hasActiveRun) setCanvasMode('agent');
  }, [hasActiveRun]);

  React.useEffect(() => {
    if (selectedDraftIndex < transcriptionDrafts.length) return;
    setSelectedDraftIndex(0);
  }, [selectedDraftIndex, transcriptionDrafts.length]);

  React.useEffect(() => {
    if (!isOpen) return;
    setEvents([]);
    setConnected(false);
    setFeedbackEntries([]);
    setFeedbackNote('');
    setFeedbackError(null);
    setPromptReceipt(null);
  }, [isOpen, sessionKey]);

  React.useEffect(() => {
    if (!isOpen) return;
    if (!isTranscribing) return;
    if (hasActiveRun) return;
    setEvents([]);
    setConnected(false);
  }, [isOpen, isTranscribing, hasActiveRun]);

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
  const allowTerminalFeedback = isRunTerminal && unresolvedRequirementsCount > 0;
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
  const layerChips = React.useMemo(() => {
    const termL1 = String(terminalSummary?.layer1_canonical_recovery || '').trim();
    const termL2 = String(terminalSummary?.layer2_canonical_sanity || '').trim();
    const termL3 = String(terminalSummary?.layer3_dependency_completeness || '').trim();
    const termClosure = String(terminalSummary?.closure_state || '').trim();
    if (termL1 || termL2 || termL3 || termClosure) {
      return {
        layer1: termL1 || 'unknown',
        layer2: termL2 || 'unknown',
        layer3: termL3 || 'unknown',
        closureState: termClosure || 'unknown',
        unresolvedCount: unresolvedRequirementsCount,
      };
    }
    if (!hasActiveRun) return null;
    const blockingOpenCount = Number(decisionSummary?.blocking_open_count || 0);
    const disputedCount = Number(decisionSummary?.disputed_count || 0);
    const hasBlockers = blockingOpenCount > 0 || disputedCount > 0;
    return {
      layer1: hasBlockers ? 'blocked' : 'in_progress',
      layer2: hasBlockers ? 'blocked' : 'in_progress',
      layer3: hasBlockers ? 'blocked' : 'in_progress',
      closureState: hasBlockers ? 'blocked' : 'in_progress',
      unresolvedCount: Math.max(0, blockingOpenCount),
    };
  }, [terminalSummary, unresolvedRequirementsCount, hasActiveRun, decisionSummary]);
  const laneChips = React.useMemo(() => buildLaneChips(orderedEvents, hasActiveRun), [orderedEvents, hasActiveRun]);
  const upstreamCorrectionRequests = React.useMemo(
    () => collectUpstreamCorrectionRequests(orderedEvents),
    [orderedEvents],
  );
  const {
    selectedArtifactJson,
    artifactError,
    loadingArtifact,
    canvasPageIndex,
    setCanvasPageIndex,
    selectedVerifyResultIndex,
    setSelectedVerifyResultIndex,
    transcriptDiffRows,
    activeImageUrl,
    verifyOriginalSize,
    imageVerifyResults,
    selectedVerifyResult,
    selectedVerifyMeta,
    previewPathD,
    availableCanvasPages,
    activeCanvasPage,
  } = useAgentViewerArtifacts({
    orderedEvents,
    canvasMode,
  });
  const {
    feedbackEntries,
    setFeedbackEntries,
    feedbackNote,
    setFeedbackNote,
    feedbackBusy,
    feedbackError,
    setFeedbackError,
    promptReceipt,
    setPromptReceipt,
    decisionOtherByKey,
    setDecisionOtherByKey,
    activeFeedbackPrompt,
    activePromptSatisfied,
    recentFeedbackEntries,
    submitFeedback,
    resendFeedbackEntry,
    requestDecisionReview,
    submitDecisionResolution,
  } = useAgentViewerFeedback({
    isOpen,
    activeLoopKind,
    activeRunId,
    isRunTerminal,
    allowTerminalFeedback,
    orderedEvents,
    canvasMode,
  });

  React.useEffect(() => {
    if (!isOpen || !activeLoopKind || !activeRunId) return;
    if (!activeFeedbackPrompt) return;
    const promptKey = `${activeRunId}:${String(activeFeedbackPrompt.promptId || '')}`;
    if (lastPromptRenderLogRef.current === promptKey) return;
    lastPromptRenderLogRef.current = promptKey;
    void fetch('http://127.0.0.1:8000/api/logs/frontend', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        level: 'INFO',
        source: 'agent_viewer_timing',
        message: `AGENT_VIEWER_TIMING ► prompt_rendered loop=${activeLoopKind} run=${activeRunId} prompt_id=${String(activeFeedbackPrompt.promptId || '')}`,
        ts: Date.now() / 1000,
        meta: {
          loop_kind: activeLoopKind,
          run_id: activeRunId,
          prompt_id: String(activeFeedbackPrompt.promptId || ''),
          blocking: Boolean(activeFeedbackPrompt.blocking),
        },
      }),
    }).catch(() => {
      // ignore timing log failures
    });
  }, [isOpen, activeLoopKind, activeRunId, activeFeedbackPrompt]);

  const submitFeedbackWithAck = React.useCallback(async (choice?: string) => {
    const result = await submitFeedback(choice);
    if (!result || !activeLoopKind || !activeRunId) return;
    if (result.activePromptId) {
      setEvents((prev) => [
        {
          protocol: 'agent_viewer_event_v1' as const,
          loop_kind: activeLoopKind,
          run_id: activeRunId,
          seq: Date.now(),
          iteration: null,
          timestamp_epoch_seconds: Math.floor(Date.now() / 1000),
          event_type: 'human_feedback',
          status: {
            stage: 'human_feedback',
            line1: 'Feedback received and queued',
            line2: result.choice || null,
          },
          artifact_refs: {},
          payload: {
            phase: 'human_feedback_received',
            stream_kind: 'narration',
            prompt_id: result.activePromptId,
            choice: result.choice || null,
          },
        },
        ...prev,
      ].slice(0, 250));
    }
  }, [submitFeedback, activeLoopKind, activeRunId, setEvents]);

  if (!isOpen) return null;

  const isSpaceTheme = theme === 'space';
  const overlayBackground = isSpaceTheme ? 'rgba(0,0,0,0.88)' : 'rgba(0,0,0,0.82)';
  const panelBackground = isSpaceTheme
    ? 'radial-gradient(circle at 20% 20%, rgba(22,27,45,0.82), #000 52%), radial-gradient(circle at 80% 70%, rgba(12,20,38,0.55), #000 60%)'
    : '#000000';
  const lensX = lensing.x.toFixed(2);
  const lensY = lensing.y.toFixed(2);
  const lensMask = `radial-gradient(180px circle at ${lensX}% ${lensY}%, rgba(255,255,255,0.98) 0%, rgba(255,255,255,0.45) 40%, rgba(255,255,255,0.12) 62%, transparent 80%)`;
  const lensShiftX = ((lensing.x - 50) * 0.28).toFixed(2);
  const lensShiftY = ((lensing.y - 50) * 0.28).toFixed(2);

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

        <AgentViewerHeader
          theme={theme}
          setTheme={setTheme}
          canvasMode={canvasMode}
          setCanvasMode={setCanvasMode}
          hasActiveRun={hasActiveRun}
          activeLoopKind={activeLoopKind}
          activeRunId={activeRunId}
          connected={connected}
          isTranscribing={isTranscribing}
          layerChips={layerChips}
          laneChips={laneChips}
          onClose={onClose}
        />

        {canvasMode === 'transcription' && (
          <TranscriptionCanvasPane
            transcriptionDrafts={transcriptionDrafts}
            selectedDraftIndex={selectedDraftIndex}
            setSelectedDraftIndex={setSelectedDraftIndex}
            isTranscribing={isTranscribing}
          />
        )}

        {canvasMode === 'agent' && (
          <div style={{ minHeight: 0, zIndex: 1, position: 'relative' }}>
            <AgentCanvasPane
              currentEvent={currentEvent}
              canvasPageIndex={canvasPageIndex}
              setCanvasPageIndex={setCanvasPageIndex}
              availableCanvasPages={availableCanvasPages}
              activeCanvasPage={activeCanvasPage}
              loadingArtifact={loadingArtifact}
              artifactError={artifactError}
              selectedArtifactJson={selectedArtifactJson}
              transcriptionFallbackText={transcriptionDrafts[Math.min(selectedDraftIndex, Math.max(transcriptionDrafts.length - 1, 0))]?.text || ''}
              transcriptDiffRows={transcriptDiffRows}
              activeImageUrl={activeImageUrl}
              verifyOriginalSize={verifyOriginalSize}
              imageVerifyResults={imageVerifyResults}
              selectedVerifyResultIndex={selectedVerifyResultIndex}
              setSelectedVerifyResultIndex={setSelectedVerifyResultIndex}
              selectedVerifyResult={selectedVerifyResult}
              selectedVerifyMeta={selectedVerifyMeta}
              previewPathD={previewPathD}
            />

            <AgentSidebar
              connected={connected}
              orderedEvents={orderedEvents}
              detailEvent={detailEvent}
              currentStatusText={currentStatusText}
              isRunTerminal={isRunTerminal}
              terminalStatus={terminalStatus}
              terminalSummary={terminalSummary}
              unresolvedRequirementsCount={unresolvedRequirementsCount}
              decisionItems={decisionItems}
              decisionSummary={decisionSummary}
              feedbackBusy={feedbackBusy}
              isHydratingReplay={isHydratingReplay}
              allowTerminalFeedback={allowTerminalFeedback}
              decisionOtherByKey={decisionOtherByKey}
              setDecisionOtherByKey={setDecisionOtherByKey}
              requestDecisionReview={requestDecisionReview}
              submitDecisionResolution={submitDecisionResolution}
              upstreamCorrectionRequests={upstreamCorrectionRequests}
              recentFeedbackEntries={recentFeedbackEntries}
              resendFeedbackEntry={resendFeedbackEntry}
            />

            <FeedbackComposer
              activeFeedbackPrompt={activeFeedbackPrompt}
              activePromptSatisfied={activePromptSatisfied}
              promptReceipt={promptReceipt}
              feedbackNote={feedbackNote}
              setFeedbackNote={setFeedbackNote}
              submitFeedbackWithAck={submitFeedbackWithAck}
              feedbackBusy={feedbackBusy}
              isRunTerminal={isRunTerminal}
              allowTerminalFeedback={allowTerminalFeedback}
              feedbackError={feedbackError}
            />

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





