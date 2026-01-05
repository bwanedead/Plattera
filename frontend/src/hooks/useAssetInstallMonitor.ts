import { useEffect, useState } from 'react';
import { assetsApi } from '../services/assets/assetApi';
import { AssetProgress } from '../types/assets';

export interface AssetInstallState {
  active: boolean;
  status: string | null;
  stage: string | null;
  message: string | null;
  percent: number | null;
  error: string | null;
}

export function useAssetInstallMonitor(assetId: string, pollMs: number = 1500): AssetInstallState {
  const [state, setState] = useState<AssetInstallState>({
    active: false,
    status: null,
    stage: null,
    message: null,
    percent: null,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      while (!cancelled) {
        try {
          const progress: AssetProgress = await assetsApi.getProgress(assetId);
          const status = progress.status || null;
          const active = status === 'installing';
          const terminal = status === 'installed' || status === 'failed' || status === 'canceled';

          if (!cancelled) {
            setState({
              active: active && !terminal,
              status,
              stage: progress.stage || null,
              message: progress.message || null,
              percent: typeof progress.percent === 'number' ? progress.percent : null,
              error: progress.error || null,
            });
          }
        } catch (e) {
          if (!cancelled) {
            setState(prev => ({
              ...prev,
              active: false,
              error: (e as Error)?.message || 'Unknown error',
            }));
          }
        }

        await new Promise(r => setTimeout(r, pollMs));
      }
    };

    poll();
    return () => {
      cancelled = true;
    };
  }, [assetId, pollMs]);

  return state;
}
