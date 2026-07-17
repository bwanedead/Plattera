import React from 'react';
import { AgentViewerShell } from './shell/AgentViewerShell';
import { useAgentViewerRun } from './hooks/useAgentViewerRun';

export function AgentViewerReplayWorkspace() {
  const run = useAgentViewerRun({
    mode: 'replay',
    isOpen: true,
  });

  return (
    <div className="av-standalone-page">
      <AgentViewerShell run={run} />
    </div>
  );
}
