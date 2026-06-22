import React from 'react';
import type { AgentViewerSnapshot } from '../../../services/agentViewerApi';

type RunHeaderProps = {
  snapshot: AgentViewerSnapshot | null;
  mode: 'live' | 'replay';
  connected: boolean;
  loading: boolean;
  error: string | null;
  onClose?: () => void;
};

export function RunHeader({ snapshot, mode, connected, loading, error, onClose }: RunHeaderProps) {
  const run = snapshot?.run;
  const status = run?.status || (loading ? 'loading' : 'idle');
  const posture =
    status === 'running'
      ? 'working'
      : status === 'completed'
        ? 'complete'
        : error
          ? 'error'
          : 'idle';

  return (
    <header className="av-run-header">
      <div className="av-run-header-main">
        <div className="av-run-eyebrow">Agent Viewer</div>
        <div className="av-run-title-row">
          <h1 className="av-run-title">{run?.run_id || 'No run selected'}</h1>
          <span className={`av-status-pill av-status-${posture}`}>{status}</span>
          <span className="av-mode-pill">{mode}</span>
        </div>
        <div className="av-run-meta">
          {run?.loop_kind ? <span>{run.loop_kind}</span> : null}
          {run?.active_chapter_id ? <span>chapter: {run.active_chapter_id}</span> : null}
          {mode === 'live' ? <span>{connected ? 'connected' : 'disconnected'}</span> : <span>replay transport</span>}
        </div>
      </div>
      {error ? <div className="av-run-error">{error}</div> : null}
      {onClose ? (
        <button type="button" className="av-button av-button-ghost" onClick={onClose}>
          Close viewer
        </button>
      ) : null}
    </header>
  );
}
