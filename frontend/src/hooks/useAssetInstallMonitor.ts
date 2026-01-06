import { useEffect, useState } from 'react';
import { assetsApi } from '../services/assets/assetApi';
import { AssetProgress } from '../types/assets';

export interface AssetInstallState {
  active: boolean;
  status: string | null;
  stage: string | null;
  message: string | null;
  headline: string | null;
  detail: string | null;
  progressBar: 'determinate' | 'indeterminate' | 'none' | null;
  percent: number | null;
  bytesDownloaded: number | null;
  bytesTotal: number | null;
  currentFile: string | null;
  phase: string | null;
  updatedAt: string | null;
  elapsedSeconds: number | null;
  error: string | null;
}

export function useAssetInstallMonitor(assetId: string, pollMs: number = 1000): AssetInstallState {
  const [state, setState] = useState<AssetInstallState>({
    active: false,
    status: null,
    stage: null,
    message: null,
    headline: null,
    detail: null,
    progressBar: null,
    percent: null,
    bytesDownloaded: null,
    bytesTotal: null,
    currentFile: null,
    phase: null,
    updatedAt: null,
    elapsedSeconds: null,
    error: null,
  });
  useEffect(() => {
    let cancelled = false;
    let installStartMs: number | null = null;

    const poll = async () => {
      while (!cancelled) {
        try {
          const progress: AssetProgress = await assetsApi.getProgress(assetId);
          const status = progress.status || null;
          const active = status === 'installing';
          const terminal = status === 'installed' || status === 'failed' || status === 'canceled';

          if (!cancelled) {
            if (active && !installStartMs) {
              installStartMs = Date.now();
            }
            if (!active) {
              installStartMs = null;
            }
            const elapsedSeconds =
              installStartMs ? Math.max(0, Math.floor((Date.now() - installStartMs) / 1000)) : null;
            setState({
              active: active && !terminal,
              status,
              stage: progress.stage || null,
              message: progress.message || null,
              headline: progress.headline || null,
              detail: progress.detail || null,
              progressBar: progress.progress_bar || null,
              percent: typeof progress.percent === 'number' ? progress.percent : null,
              bytesDownloaded:
                typeof progress.bytes_downloaded === 'number' ? progress.bytes_downloaded : null,
              bytesTotal: typeof progress.bytes_total === 'number' ? progress.bytes_total : null,
              currentFile: progress.current_file || null,
              phase: progress.phase || null,
              updatedAt: progress.updated_at || null,
              elapsedSeconds,
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
