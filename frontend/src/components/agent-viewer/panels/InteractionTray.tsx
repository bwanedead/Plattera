import React from 'react';
import type { NormalizedHitlPrompt } from '../model/viewTypes';

type InteractionTrayProps = {
  activePrompt: NormalizedHitlPrompt | null;
  note: string;
  onNoteChange: (value: string) => void;
  busy: boolean;
  error: string | null;
  receipt: string | null;
  onSubmitChoice: (choice: string) => void;
  onSubmitSteering: () => void;
  selectionLabel: string | null;
};

export function InteractionTray({
  activePrompt,
  note,
  onNoteChange,
  busy,
  error,
  receipt,
  onSubmitChoice,
  onSubmitSteering,
  selectionLabel,
}: InteractionTrayProps) {
  return (
    <section className="av-interaction-tray">
      <div className="av-interaction-header">
        <span className="av-interaction-title">Interaction</span>
        {activePrompt?.blocking ? <span className="av-badge av-badge-blocking">Blocking</span> : null}
        {selectionLabel ? <span className="av-meta-chip">Context: {selectionLabel}</span> : null}
      </div>

      {activePrompt ? (
        <div className="av-hitl-prompt">
          <div className="av-hitl-question">{activePrompt.question}</div>
          {activePrompt.detail ? <div className="av-hitl-detail">{activePrompt.detail}</div> : null}
          {activePrompt.choices.length ? (
            <div className="av-hitl-choices">
              {activePrompt.choices.map((choice) => (
                <button
                  key={choice}
                  type="button"
                  className="av-button av-button-primary"
                  disabled={busy}
                  onClick={() => onSubmitChoice(choice)}
                >
                  {choice}
                </button>
              ))}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="av-hitl-idle">No blocking prompt. Send steering context below when needed.</div>
      )}

      <div className="av-steering-row">
        <textarea
          className="av-steering-input"
          value={note}
          onChange={(event) => onNoteChange(event.target.value)}
          placeholder="Add context-addressed guidance for the agent…"
          rows={2}
        />
        <button type="button" className="av-button" disabled={busy || !note.trim()} onClick={onSubmitSteering}>
          Send
        </button>
      </div>

      {error ? <div className="av-run-error">{error}</div> : null}
      {receipt ? <div className="av-interaction-receipt">{receipt}</div> : null}
    </section>
  );
}
