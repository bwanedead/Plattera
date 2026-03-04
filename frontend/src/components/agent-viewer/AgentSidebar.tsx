import React from 'react';
import type { AgentViewerEvent, AgentViewerFeedbackEntry } from '../../services/agentViewerApi';
import { DecisionChecklistPanel } from './DecisionChecklistPanel';
import { EventDetailBlock } from './EventDetailBlock';
import { summarizeEventForesight } from './agentViewerUtils';
import type { DecisionLedgerItem } from './types';

type Props = {
  connected: boolean;
  orderedEvents: AgentViewerEvent[];
  detailEvent: AgentViewerEvent | null;
  currentStatusText: string;
  isRunTerminal: boolean;
  terminalStatus: 'completed' | 'needs_review' | 'failed' | null;
  terminalSummary: Record<string, any> | null;
  unresolvedRequirementsCount: number;
  decisionItems: DecisionLedgerItem[];
  decisionSummary: Record<string, any> | null;
  feedbackBusy: boolean;
  isHydratingReplay: boolean;
  decisionOtherByKey: Record<string, string>;
  setDecisionOtherByKey: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  requestDecisionReview: (decisionKey: string) => void;
  submitDecisionResolution: (decisionKey: string, choice: string | null, extraNote?: string | null) => void;
  upstreamCorrectionRequests: Array<Record<string, any>>;
  recentFeedbackEntries: AgentViewerFeedbackEntry[];
  resendFeedbackEntry: (entry: AgentViewerFeedbackEntry) => void;
};

export function AgentSidebar({
  connected,
  orderedEvents,
  detailEvent,
  currentStatusText,
  isRunTerminal,
  terminalStatus,
  terminalSummary,
  unresolvedRequirementsCount,
  decisionItems,
  decisionSummary,
  feedbackBusy,
  isHydratingReplay,
  decisionOtherByKey,
  setDecisionOtherByKey,
  requestDecisionReview,
  submitDecisionResolution,
  upstreamCorrectionRequests,
  recentFeedbackEntries,
  resendFeedbackEntry,
}: Props) {
  const floatingHistory = orderedEvents.slice(0, 14).map((evt, idx) => ({
    idx,
    text: summarizeEventForesight(evt),
    iteration: evt.iteration,
    isCurrent: idx === 0,
    isTicker: String(evt.payload?.stream_kind || 'narration') === 'ticker',
    isReplay: Boolean(evt.payload?.__replay),
  }));

  return (
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
          <div>Closure State: {String(terminalSummary.closure_state || 'unknown')}</div>
          <div>Unresolved Requirements: {unresolvedRequirementsCount}</div>
          <div>Edits Applied: {Number(terminalSummary.edits_applied_total || 0)}</div>
          <div>HITL Used: {terminalSummary.used_human_feedback ? 'yes' : 'no'}</div>
        </div>
      )}

      <DecisionChecklistPanel
        decisionItems={decisionItems}
        decisionSummary={decisionSummary}
        feedbackBusy={feedbackBusy}
        isRunTerminal={isRunTerminal}
        decisionOtherByKey={decisionOtherByKey}
        setDecisionOtherByKey={setDecisionOtherByKey}
        requestDecisionReview={requestDecisionReview}
        submitDecisionResolution={submitDecisionResolution}
      />

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
      {isHydratingReplay && (
        <div style={{ padding: '6px 12px', borderTop: '1px solid rgba(255,255,255,0.06)', fontSize: 10, opacity: 0.7 }}>
          Hydrating recent event replay…
        </div>
      )}
    </div>
  );
}
