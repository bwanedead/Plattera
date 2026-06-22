import React from 'react';
import { acquireAgentViewerClientLogBridge } from '../transport/live/frontendLogGateway';

export function useAgentViewerClientLogBridge(enabled: boolean): void {
  React.useEffect(() => {
    if (!enabled) return;
    return acquireAgentViewerClientLogBridge();
  }, [enabled]);
}
