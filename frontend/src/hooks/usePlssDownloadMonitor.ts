import { useEffect, useState } from 'react';
import { plssDataService } from '../services/plss';

export interface PlssDownloadState {
  active: boolean;
  state: string | null;
  stage: string | null;
  percent: number | null;
  text: string | null;
}

/**
 * Global PLSS download monitor.
 * 
 * Uses the last state that was started for background download (tracked
 * in localStorage by usePLSSData) and polls the backend status/progress
 * endpoints until the job reaches a terminal state.
 */
export function usePlssDownloadMonitor(): PlssDownloadState {
  const [download, setDownload] = useState<PlssDownloadState>({
    active: false,
    state: null,
    stage: null,
    percent: null,
    text: null,
  });

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        let lastState: string | null = null;
        try {
          lastState = localStorage.getItem('plss:lastState');
        } catch {
          lastState = null;
        }

        if (!lastState) {
          // No known state - nothing to monitor
          if (!cancelled) {
            setDownload(prev => ({
              ...prev,
              active: false,
              state: null,
              stage: null,
              percent: null,
              text: null,
            }));
          }
        } else {
          try {
            // First, check if the backend reports this state as active
            const status = await plssDataService.checkDownloadActive(lastState);
            if (status.active) {
              const progress = await plssDataService.getDownloadProgress(lastState);
              const overall = progress.overall || { percent: 0 };
              const stage = progress.stage || status.stage || 'working';
              const text = (progress as any).status || stage || null;

              if (!cancelled) {
                setDownload({
                  active: true,
                  state: lastState,
                  stage,
                  percent: typeof overall.percent === 'number' ? overall.percent : null,
                  text,
                });
              }
            } else {
              // Not reported active; peek once at progress to see if we just finished
              const progress = await plssDataService.getDownloadProgress(lastState);
              const stage = progress.stage || 'idle';
              const overall = progress.overall || { percent: 0 };

              const isTerminal =
                stage === 'complete' ||
                stage === 'idle' ||
                stage === 'canceled';

              if (!cancelled) {
                setDownload(prev => ({
                  ...prev,
                  active: !isTerminal,
                  state: isTerminal ? null : lastState,
                  stage: stage,
                  percent: typeof overall.percent === 'number' ? overall.percent : null,
                  text: (progress as any).status || stage || null,
                }));
              }

              // If terminal, we can stop advertising activity but still keep
              // lastState in storage for future diagnostics.
            }
          } catch {
            // On error, do not crash the monitor; just mark as inactive for now.
            if (!cancelled) {
              setDownload(prev => ({
                ...prev,
                active: false,
                state: null,
                stage: null,
                percent: null,
                text: null,
              }));
            }
          }
        }

        // Poll interval – keep it modest to avoid hammering the backend.
        await new Promise(r => setTimeout(r, 1500));
      }
    };

    poll();
    return () => {
      cancelled = true;
    };
  }, []);

  return download;
}

