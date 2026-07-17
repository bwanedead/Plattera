import React from 'react';
import type { AgentViewerEvent } from '../../../services/agentViewerApi';
import { viewerEventIdentity, viewerEventLabel } from '../model/eventIdentity';
import { useViewerSelection } from '../selection/useViewerSelection';

type Params = {
  orderedEvents: AgentViewerEvent[];
};

export function useAgentViewerShellState({ orderedEvents }: Params) {
  const { selection, followLive, select, selectLive, resumeFollowLive } = useViewerSelection();
  const [rawOpen, setRawOpen] = React.useState(false);
  const [observabilityOpen, setObservabilityOpen] = React.useState(false);

  const toggleRaw = React.useCallback(() => {
    setRawOpen((value) => !value);
  }, []);

  const toggleObservability = React.useCallback(() => {
    setObservabilityOpen((value) => !value);
  }, []);

  React.useEffect(() => {
    if (!followLive) return;
    const latest = orderedEvents[0];
    if (!latest) return;
    selectLive({
      kind: 'event',
      id: viewerEventIdentity(latest),
      label: viewerEventLabel(latest),
      payload: { event: latest },
    });
  }, [followLive, orderedEvents, selectLive]);

  return {
    selection,
    followLive,
    select,
    selectLive,
    resumeFollowLive,
    rawOpen,
    setRawOpen,
    toggleRaw,
    observabilityOpen,
    setObservabilityOpen,
    toggleObservability,
  };
}
