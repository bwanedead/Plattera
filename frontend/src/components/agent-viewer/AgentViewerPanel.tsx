import React from 'react';
import { AgentViewerShell } from './shell/AgentViewerShell';
import { useAgentViewerRun } from './hooks/useAgentViewerRun';
import type { AgentViewerPanelProps } from './types';

/**
 * Live-run overlay entrypoint. Workspaces import this component only;
 * implementation is the native universal shell (no legacy viewer path).
 */
export const AgentViewerPanel: React.FC<AgentViewerPanelProps> = ({
  isOpen,
  loopKind,
  runId,
  onClose,
}) => {
  const run = useAgentViewerRun({
    mode: 'live',
    isOpen,
    loopKind,
    runId,
  });

  if (!isOpen) return null;

  return (
    <div
      className="av-overlay-scrim"
      onClick={onClose}
      role="presentation"
    >
      <div
        className="av-overlay-frame"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
        aria-label="Agent viewer"
      >
        <AgentViewerShell run={run} onClose={onClose} />
      </div>
    </div>
  );
};
