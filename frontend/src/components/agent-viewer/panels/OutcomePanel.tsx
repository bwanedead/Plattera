import React from 'react';
import type { OutcomeView } from '../model/viewTypes';

type OutcomePanelProps = {
  outcome: OutcomeView;
};

export function OutcomePanel({ outcome }: OutcomePanelProps) {
  if (!outcome.isTerminal) return null;

  return (
    <section className="av-outcome-panel">
      <div className="av-outcome-title">Outcome</div>
      <div className="av-outcome-status">{outcome.status}</div>
      {outcome.summary ? <div className="av-outcome-summary">{outcome.summary}</div> : null}
    </section>
  );
}
