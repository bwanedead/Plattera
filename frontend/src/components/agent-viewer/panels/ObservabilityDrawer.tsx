import React from 'react';
import type { ObservabilityView } from '../model/observabilityModel';

type ObservabilityDrawerProps = {
  open: boolean;
  view: ObservabilityView;
  onClose: () => void;
};

function formatSeconds(value: number): string {
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}m ${seconds.toFixed(0)}s`;
}

export function ObservabilityDrawer({ open, view, onClose }: ObservabilityDrawerProps) {
  if (!open) return null;

  return (
    <aside className="av-observability-drawer" aria-label="Run observability">
      <div className="av-observability-header">
        <span className="av-observability-title">Observability</span>
        <button type="button" className="av-button av-button-ghost" onClick={onClose}>
          Close
        </button>
      </div>

      <div className="av-observability-summary">
        <div className="av-obs-summary-card">
          <span className="av-obs-summary-label">Duration</span>
          <span className="av-obs-summary-value">{formatSeconds(view.totalDurationSeconds)}</span>
        </div>
        <div className="av-obs-summary-card">
          <span className="av-obs-summary-label">Tokens</span>
          <span className="av-obs-summary-value">{view.totalTokens.toLocaleString()}</span>
        </div>
        <div className="av-obs-summary-card">
          <span className="av-obs-summary-label">Delegates</span>
          <span className="av-obs-summary-value">{view.delegateEventCount}</span>
        </div>
        {view.activeTurn != null ? (
          <div className="av-obs-summary-card">
            <span className="av-obs-summary-label">Turn</span>
            <span className="av-obs-summary-value">T{view.activeTurn}</span>
          </div>
        ) : null}
      </div>

      <div className="av-observability-table-wrap">
        <table className="av-observability-table">
          <thead>
            <tr>
              <th>Turn</th>
              <th>Duration</th>
              <th>Tokens</th>
              <th>Delegates</th>
              <th>Posture</th>
            </tr>
          </thead>
          <tbody>
            {view.rows.length ? (
              view.rows.map((row) => (
                <tr key={row.turnIndex}>
                  <td>T{row.turnIndex}</td>
                  <td>{row.durationSeconds != null ? formatSeconds(row.durationSeconds) : '—'}</td>
                  <td>
                    {typeof row.tokenUsage.total === 'number'
                      ? row.tokenUsage.total.toLocaleString()
                      : '—'}
                  </td>
                  <td>{row.delegateActionCount || '—'}</td>
                  <td>{row.posture || '—'}</td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={5} className="av-empty-inline">
                  No turn telemetry yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </aside>
  );
}
