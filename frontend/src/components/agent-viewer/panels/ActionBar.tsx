import React from 'react';
import type { ViewerActionView } from '../hooks/useAgentViewerActions';

type ActionBarProps = {
  actions: ViewerActionView[];
  busyId: string | null;
  lastResult: { actionId: string; ok: boolean; reason?: string } | null;
};

export function ActionBar({ actions, busyId, lastResult }: ActionBarProps) {
  if (!actions.length) return null;

  return (
    <div className="av-action-bar">
      <span className="av-action-bar-label">Actions</span>
      <div className="av-action-bar-items">
        {actions.map((action) => (
          <button
            key={action.id}
            type="button"
            className="av-button"
            disabled={action.disabled || busyId === action.id}
            title={action.reason || undefined}
            onClick={action.onExecute}
          >
            {action.label}
          </button>
        ))}
      </div>
      {lastResult && !lastResult.ok ? (
        <span className="av-action-bar-error">{lastResult.reason || 'Action failed'}</span>
      ) : null}
    </div>
  );
}
