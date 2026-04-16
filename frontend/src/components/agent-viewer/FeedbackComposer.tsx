import React from 'react';
import { getAgentViewerArtifactImageUrl } from '../../services/agentViewerApi';
import type { ActivePrompt } from './hooks/useAgentViewerFeedback';

type Props = {
  activeFeedbackPrompt: ActivePrompt | null;
  activePromptSatisfied: boolean;
  promptReceipt: string | null;
  feedbackNote: string;
  setFeedbackNote: React.Dispatch<React.SetStateAction<string>>;
  submitFeedbackWithAck: (choice?: string) => void;
  feedbackBusy: boolean;
  isRunTerminal: boolean;
  allowTerminalFeedback: boolean;
  feedbackError: string | null;
};

export function FeedbackComposer({
  activeFeedbackPrompt,
  activePromptSatisfied,
  promptReceipt,
  feedbackNote,
  setFeedbackNote,
  submitFeedbackWithAck,
  feedbackBusy,
  isRunTerminal,
  allowTerminalFeedback,
  feedbackError,
}: Props) {
  const terminalLocked = isRunTerminal && !allowTerminalFeedback;
  const evidencePreviewRefs = activeFeedbackPrompt ? buildEvidencePreviewRefs(activeFeedbackPrompt) : [];
  return (
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
          {activeFeedbackPrompt.synthetic && (
            <div style={{ fontSize: 10, opacity: 0.68, marginTop: 3 }}>
              Generated from unresolved closure requirements.
            </div>
          )}
          {!activeFeedbackPrompt.blocking && (
            <div style={{ fontSize: 10, opacity: 0.66, marginTop: 3 }}>
              Optional feedback: the loop can continue while this remains unanswered.
            </div>
          )}
          <div style={{ fontSize: 10, opacity: 0.64, marginTop: 3 }}>prompt_id: {activeFeedbackPrompt.promptId}</div>
          {activeFeedbackPrompt.questionRegions.length > 0 && (
            <div style={{ fontSize: 10, opacity: 0.7, marginTop: 4 }}>
              Question regions: {activeFeedbackPrompt.questionRegions.join(' | ')}
            </div>
          )}
          {evidencePreviewRefs.length > 0 && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 8, marginTop: 8 }}>
              {evidencePreviewRefs.map((artifactRef) => (
                <div key={artifactRef} style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid rgba(255,255,255,0.14)', background: 'rgba(255,255,255,0.03)' }}>
                  <img
                    src={getAgentViewerArtifactImageUrl(artifactRef)}
                    alt="HITL evidence"
                    style={{ display: 'block', width: '100%', maxHeight: 180, objectFit: 'contain', background: 'rgba(255,255,255,0.02)' }}
                  />
                  <div style={{ fontSize: 10, opacity: 0.68, padding: '6px 8px', wordBreak: 'break-all' }}>
                    {artifactRef}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {!activeFeedbackPrompt && promptReceipt && (
        <div style={{ marginBottom: 8, fontSize: 11, color: '#8ee5b0' }}>
          {promptReceipt}
        </div>
      )}

      {activeFeedbackPrompt?.choices?.length ? (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
          {activeFeedbackPrompt.choices.map((choice) => (
            <button key={choice} onClick={() => submitFeedbackWithAck(choice)} disabled={feedbackBusy || activePromptSatisfied || terminalLocked} style={{ fontSize: 11, borderRadius: 999, padding: '4px 8px' }}>
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
        <button onClick={() => submitFeedbackWithAck()} disabled={feedbackBusy || activePromptSatisfied || terminalLocked} style={{ height: 34, borderRadius: 8, padding: '0 10px', fontSize: 12 }}>
          {feedbackBusy ? 'Sending…' : 'Send'}
        </button>
      </div>

      {feedbackError && <div style={{ marginTop: 6, fontSize: 11, color: '#ff9aa0' }}>{feedbackError}</div>}
      {activePromptSatisfied && <div style={{ marginTop: 6, fontSize: 11, color: '#8ee5b0' }}>Prompt response received.</div>}
    </div>
  );
}

function buildEvidencePreviewRefs(activeFeedbackPrompt: ActivePrompt): string[] {
  const refs = [
    activeFeedbackPrompt.annotatedEvidenceRef,
    activeFeedbackPrompt.primaryEvidenceRef,
    ...activeFeedbackPrompt.evidenceRefs,
  ].filter((value): value is string => Boolean(value));
  return Array.from(new Set(refs)).slice(0, 2);
}
