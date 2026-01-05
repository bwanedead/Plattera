import React, { useEffect, useRef, useState } from 'react';
import { assetsApi } from '../../services/assets/assetApi';
import { AssetRow } from '../../types/assets';
import { plssDataService } from '../../services/plss';
import { AssetInstallModal } from './AssetInstallModal';

interface AssetsTrayProps {
  open: boolean;
  onClose: () => void;
}

const EMBEDDING_ASSET_ID = 'embedding_model_bge_small_en_v1_5';

const buildSnapshot = (rows: AssetRow[]) =>
  JSON.stringify(
    rows.map((row) => ({
      asset_id: row.asset_id,
      status: row.status,
      stage: row.stage ?? null,
      message: row.message ?? null,
      percent: typeof row.percent === 'number' ? row.percent : null,
      manifest_revision: row.manifest?.revision ?? null,
      manifest_total_bytes: row.manifest?.total_bytes ?? null,
      plss_state: row.plss_state ?? null,
    })),
  );

export const AssetsTray: React.FC<AssetsTrayProps> = ({ open, onClose: _onClose }) => {
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [plssState, setPlssState] = useState<string>('Wyoming');
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const initialFetchDoneRef = useRef(false);
  const lastSnapshotRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) {
      initialFetchDoneRef.current = false;
      lastSnapshotRef.current = null;
      setLoading(false);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        const showLoading = !initialFetchDoneRef.current;
        if (showLoading) {
          setLoading(true);
        }
        let list: AssetRow[] | null = null;
        let nextDelay = 35000;
        try {
          list = await assetsApi.listAssets(plssState);
          if (!cancelled) {
            const snapshot = buildSnapshot(list);
            if (snapshot !== lastSnapshotRef.current) {
              setAssets(list);
              lastSnapshotRef.current = snapshot;
            }
            setError(null);
          }
        } catch (e: any) {
          if (!cancelled) {
            setError(e?.message || 'Failed to load assets');
          }
        } finally {
          if (!cancelled && showLoading) {
            setLoading(false);
            initialFetchDoneRef.current = true;
          }
        }
        if (list && list.some(asset => asset.status === 'installing')) {
          nextDelay = 2000;
        }
        await new Promise(r => setTimeout(r, nextDelay));
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [open, plssState]);

  if (!open) return null;

  const embedding = assets.find(a => a.asset_id === EMBEDDING_ASSET_ID);
  const plss = assets.find(a => a.asset_id === 'plss');
  const plssInstalled = plss?.status === 'installed';
  const embeddingInstalled = embedding?.status === 'installed';
  const embeddingInstalling = embedding?.status === 'installing';
  const embeddingMissing =
    embedding?.status === 'missing' || embedding?.status === 'failed' || embedding?.status === 'canceled';

  const badgeStyles = (tone: 'good' | 'warn' | 'info') => {
    const palettes = {
      good: { bg: '#14532d', border: '#22c55e', text: '#dcfce7' },
      warn: { bg: '#78350f', border: '#f59e0b', text: '#fef3c7' },
      info: { bg: '#1e3a8a', border: '#60a5fa', text: '#dbeafe' },
    };
    const palette = palettes[tone];
    return {
      display: 'inline-flex',
      alignItems: 'center',
      gap: 6,
      padding: '6px 12px',
      borderRadius: 999,
      background: palette.bg,
      border: `1px solid ${palette.border}`,
      color: palette.text,
      fontWeight: 600,
      fontSize: 12,
    } as const;
  };

  const handleEmbeddingInstall = async () => {
    if (!embedding) return;
    setInstalling(true);
    try {
      await assetsApi.installAsset(embedding.asset_id);
      try {
        localStorage.setItem(`asset:last:${embedding.asset_id}`, 'true');
        localStorage.removeItem(`asset:overlayDismissed:${embedding.asset_id}`);
      } catch {
        // ignore
      }
    } catch (e) {
      console.error('Embedding install failed', e);
    } finally {
      setInstalling(false);
      setInstallModalOpen(false);
    }
  };

  const handlePlssInstall = async () => {
    if (!plssState) return;
    try {
      localStorage.setItem('plss:lastState', plssState);
      localStorage.removeItem(`plss:overlayDismissed:${plssState}`);
    } catch {
      // ignore
    }
    try {
      document.dispatchEvent(new Event('plss:open-modal'));
    } catch (e) {
      console.error('Failed to dispatch plss:open-modal', e);
    }
    await plssDataService.startBackgroundDownload(plssState);
  };

  const handleCancelEmbedding = async () => {
    if (!embedding) return;
    try {
      await assetsApi.cancel(embedding.asset_id);
    } catch (e) {
      console.error('Cancel failed', e);
    }
  };

  const handlePurgeEmbedding = async () => {
    if (!embedding) return;
    try {
      await assetsApi.purge(embedding.asset_id);
    } catch (e) {
      console.error('Purge failed', e);
    }
  };

  return (
    <div>
      {error && <div style={{ marginTop: 12, color: '#fca5a5' }}>{error}</div>}
      {loading && <div style={{ marginTop: 8, color: '#94a3b8' }}>Loading...</div>}

      <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
        <div style={{ padding: 12, borderRadius: 10, background: '#0f172a' }}>
          <div style={{ fontWeight: 600 }}>PLSS data</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8 }}>
            <label style={{ fontSize: 12, color: '#cbd5f5' }}>State</label>
            <input
              value={plssState}
              onChange={(e) => setPlssState(e.target.value)}
              style={{
                background: '#0b1220',
                color: '#f8fafc',
                border: '1px solid rgba(148, 163, 184, 0.3)',
                borderRadius: 6,
                padding: '4px 8px',
              }}
            />
            {plssInstalled ? (
              <span style={{ ...badgeStyles('good'), fontSize: 12 }}>Ready</span>
            ) : (
              <button
                onClick={handlePlssInstall}
                style={{
                  background: '#2563eb',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                Download PLSS
              </button>
            )}
          </div>
        </div>

        <div style={{ padding: 12, borderRadius: 10, background: '#0f172a' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div style={{ fontWeight: 600 }}>Embedding model (bge-small-en-v1.5)</div>
            {embeddingInstalling ? (
              <span style={badgeStyles('info')}>Installing</span>
            ) : embeddingInstalled ? (
              <span style={badgeStyles('good')}>Installed</span>
            ) : (
              <span style={badgeStyles('warn')}>Not installed</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
            {embeddingMissing && (
              <button
                onClick={() => setInstallModalOpen(true)}
                style={{
                  background: '#4f46e5',
                  color: '#fff',
                  border: 'none',
                  padding: '6px 12px',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                Install
              </button>
            )}
            {embeddingInstalling && (
              <button
                onClick={handleCancelEmbedding}
                style={{
                  background: 'transparent',
                  color: '#f87171',
                  border: '1px solid #f87171',
                  padding: '6px 12px',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
            )}
            {embeddingInstalled && (
              <button
                onClick={handlePurgeEmbedding}
                style={{
                  background: 'transparent',
                  color: '#f59e0b',
                  border: '1px solid #f59e0b',
                  padding: '6px 12px',
                  borderRadius: 6,
                  cursor: 'pointer',
                }}
              >
                Purge
              </button>
            )}
          </div>
          {embeddingInstalling && (
            <div style={{ marginTop: 8, fontSize: 12, color: '#94a3b8' }}>
              Cancel stops after the current download step completes.
            </div>
          )}
        </div>
      </div>

      <AssetInstallModal
        open={installModalOpen}
        assetName="Embedding model (bge-small-en-v1.5)"
        onConfirm={handleEmbeddingInstall}
        onClose={() => setInstallModalOpen(false)}
        isInstalling={installing}
      />
    </div>
  );
};
