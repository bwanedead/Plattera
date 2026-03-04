import React from 'react';
import type { DecisionLedgerItem } from './types';

function closureReasonLabel(reason: string): string {
  const r = String(reason || '').toLowerCase();
  if (r === 'ambiguity') return 'Layer 1 Ambiguity';
  if (r === 'contradiction') return 'Layer 2 Contradiction';
  if (r === 'dependency') return 'Layer 3 Dependency';
  return 'Closure Needed';
}

type DecisionChecklistPanelProps = {
  decisionItems: DecisionLedgerItem[];
  decisionSummary: Record<string, any> | null;
  feedbackBusy: boolean;
  isRunTerminal: boolean;
  decisionOtherByKey: Record<string, string>;
  setDecisionOtherByKey: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  requestDecisionReview: (decisionKey: string) => void;
  submitDecisionResolution: (decisionKey: string, choice: string | null, extraNote?: string | null) => void;
};

export function DecisionChecklistPanel({
  decisionItems,
  decisionSummary,
  feedbackBusy,
  isRunTerminal,
  decisionOtherByKey,
  setDecisionOtherByKey,
  requestDecisionReview,
  submitDecisionResolution,
}: DecisionChecklistPanelProps) {
  if (decisionItems.length <= 0) return null;
  const prioritizedItems = [...decisionItems].sort((a, b) => {
    const aBlocking = Boolean(a.blocking);
    const bBlocking = Boolean(b.blocking);
    if (aBlocking !== bBlocking) return aBlocking ? -1 : 1;
    const aState = String(a.state || '').toLowerCase();
    const bState = String(b.state || '').toLowerCase();
    const aNeeds = aState === 'disputed' || aState === 'open';
    const bNeeds = bState === 'disputed' || bState === 'open';
    if (aNeeds !== bNeeds) return aNeeds ? -1 : 1;
    const aClosure = Boolean(a.closure_requirement);
    const bClosure = Boolean(b.closure_requirement);
    if (aClosure !== bClosure) return aClosure ? -1 : 1;
    return 0;
  });
  const topActionable = prioritizedItems.find((item) => {
    const state = String(item.state || '').toLowerCase();
    return Boolean(item.blocking) || state === 'disputed' || state === 'open';
  }) || null;
  return (
    <div style={{ padding: '8px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', fontSize: 11, lineHeight: 1.35 }}>
      <div style={{ fontSize: 11, opacity: 0.85, marginBottom: 6 }}>Decision Checklist</div>
      {decisionSummary && (
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6, opacity: 0.78 }}>
          <span>Open: {Number(decisionSummary.blocking_open_count || 0)}</span>
          <span>Verified: {Number(decisionSummary.verified_count || 0)}</span>
          <span>Disputed: {Number(decisionSummary.disputed_count || 0)}</span>
        </div>
      )}
      {topActionable && (
        <div style={{ marginBottom: 8, border: '1px solid rgba(255,171,64,0.32)', borderRadius: 8, padding: '6px 7px', background: 'rgba(255,171,64,0.08)' }}>
          <div style={{ fontSize: 10, opacity: 0.88, marginBottom: 3 }}>
            Action Needed Now
          </div>
          <div style={{ fontSize: 11, opacity: 0.95 }}>
            {String(topActionable.label || topActionable.key || 'decision')} {topActionable.selected_value ? `(${String(topActionable.selected_value)})` : ''}
          </div>
          {topActionable.closure_requirement?.minimal_user_action && (
            <div style={{ fontSize: 10, opacity: 0.82, marginTop: 2 }}>
              {String(topActionable.closure_requirement.minimal_user_action)}
            </div>
          )}
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 240, overflowY: 'auto' }}>
        {prioritizedItems.slice(0, 10).map((item, idx) => {
          const state = String(item.state || 'unknown');
          const blocking = Boolean(item.blocking);
          const decisionKey = String(item.key || '');
          const closure = item.closure_requirement && typeof item.closure_requirement === 'object'
            ? item.closure_requirement
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
                    <span
                      style={{
                        fontSize: 10,
                        padding: '1px 6px',
                        borderRadius: 999,
                        background: closure.mapping_blocking ? 'rgba(255,107,107,0.2)' : 'rgba(142,197,255,0.2)',
                        border: '1px solid rgba(255,255,255,0.2)',
                      }}
                    >
                      {closure.mapping_blocking ? 'mapping-blocking' : 'optional'}
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
  );
}
