import React from 'react';
import { installAgentViewerClientLogBridge } from '../transport/live/frontendLogGateway';

export function useAgentViewerClientLogBridge(enabled: boolean): void {
  React.useEffect(() => {
    if (!enabled) return;
    return installAgentViewerClientLogBridge();
  }, [enabled]);
}
