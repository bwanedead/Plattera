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
  sessionKey,
  onClose,
}) => {
  const run = useAgentViewerRun({
    mode: 'live',
    isOpen,
    loopKind,
    runId,
  });

  React.useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const shellKey = sessionKey || runId || 'agent-viewer-live';

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
        aria-modal="true"
      >
        <AgentViewerShell key={shellKey} run={run} onClose={onClose} />
      </div>
    </div>
  );
};
