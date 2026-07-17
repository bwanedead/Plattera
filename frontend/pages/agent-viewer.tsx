import React from 'react';
import dynamic from 'next/dynamic';

const AgentViewerReplayWorkspace = dynamic(
  () =>
    import('../src/components/agent-viewer/AgentViewerReplayWorkspace').then((mod) => ({
      default: mod.AgentViewerReplayWorkspace,
    })),
  { ssr: false },
);

export default function AgentViewerPage() {
  return <AgentViewerReplayWorkspace />;
}
