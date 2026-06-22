import React from 'react';
import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';
import type { ViewerRunPosture } from '../model/viewTypes';

type RunHeaderProps = {
  snapshot: AgentViewerSnapshot | null;
  mode: 'live' | 'replay';
  connected: boolean;
  loading: boolean;
  error: string | null;
  posture: ViewerRunPosture;
  observabilityOpen?: boolean;
  onToggleObservability?: () => void;
  onClose?: () => void;
};

const POSTURE_LABEL: Record<ViewerRunPosture, string> = {
  idle: 'idle',
  loading: 'loading',
  working: 'working',
  waiting_user: 'waiting on you',
  disconnected: 'disconnected',
  terminal: 'complete',
  error: 'error',
};

export function RunHeader({
  snapshot,
  mode,
  connected,
  loading,
  error,
  posture,
  observabilityOpen,
  onToggleObservability,
  onClose,
}: RunHeaderProps) {
  const run = snapshot?.run;
  const status = run?.status || (loading ? 'loading' : 'idle');

  return (
    <header className="av-run-header">
      <div className="av-run-header-main">
        <div className="av-run-eyebrow">Agent Viewer</div>
        <div className="av-run-title-row">
          <h1 className="av-run-title">{run?.run_id || 'No run selected'}</h1>
          <span className={`av-status-pill av-status-${posture}`}>{POSTURE_LABEL[posture]}</span>
          <span className="av-mode-pill">{mode}</span>
          {status ? <span className="av-meta-chip">{status}</span> : null}
        </div>
        <div className="av-run-meta">
          {run?.loop_kind ? <span>{run.loop_kind}</span> : null}
          {run?.active_chapter_id ? <span>chapter: {run.active_chapter_id}</span> : null}
          {mode === 'live' ? <span>{connected ? 'connected' : 'disconnected'}</span> : <span>replay transport</span>}
        </div>
      </div>
      {error ? <div className="av-run-error">{error}</div> : null}
      <div className="av-run-header-actions">
        {onToggleObservability ? (
          <button
            type="button"
            className={`av-button av-button-ghost ${observabilityOpen ? 'is-active' : ''}`}
            onClick={onToggleObservability}
          >
            Observability
          </button>
        ) : null}
        {onClose ? (
          <button type="button" className="av-button av-button-ghost" onClick={onClose}>
            Close viewer
          </button>
        ) : null}
      </div>
    </header>
  );
}
