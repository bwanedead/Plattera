import React, { useEffect, useState } from 'react';
import { assetsApi } from '../../services/assets/assetApi';
import { AssetRow } from '../../types/assets';
import { plssDataService } from '../../services/plss';
import { AssetInstallModal } from './AssetInstallModal';

interface AssetsTrayProps {
  open: boolean;
  onClose: () => void;
}

const EMBEDDING_ASSET_ID = 'embedding_model_bge_small_en_v1_5';

export const AssetsTray: React.FC<AssetsTrayProps> = ({ open, onClose }) => {
  const [assets, setAssets] = useState<AssetRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [plssState, setPlssState] = useState<string>('Wyoming');
  const [installModalOpen, setInstallModalOpen] = useState(false);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        try {
          setLoading(true);
          const list = await assetsApi.listAssets(plssState);
          if (!cancelled) {
            setAssets(list);
            setError(null);
          }
        } catch (e: any) {
          if (!cancelled) {
            setError(e?.message || 'Failed to load assets');
          }
        } finally {
          if (!cancelled) setLoading(false);
        }
        await new Promise(r => setTimeout(r, 2000));
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
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        zIndex: 1200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#111827',
          color: '#f9fafb',
          width: 640,
          borderRadius: 12,
          padding: 20,
          border: '1px solid rgba(255,255,255,0.08)',
          boxShadow: '0 30px 60px rgba(0,0,0,0.6)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <h3 style={{ margin: 0 }}>Assets</h3>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              color: '#e2e8f0',
              padding: '6px 12px',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
        {error && <div style={{ marginTop: 12, color: '#fca5a5' }}>{error}</div>}
        {loading && <div style={{ marginTop: 8, color: '#94a3b8' }}>Loading…</div>}

        <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ padding: 12, borderRadius: 10, background: '#0f172a' }}>
            <div style={{ fontWeight: 600 }}>PLSS data</div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>
              Status: {plss?.status || 'unknown'} {plss?.message ? `— ${plss.message}` : ''}
            </div>
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
            </div>
          </div>

          <div style={{ padding: 12, borderRadius: 10, background: '#0f172a' }}>
            <div style={{ fontWeight: 600 }}>Embedding model (bge-small-en-v1.5)</div>
            <div style={{ fontSize: 12, color: '#94a3b8' }}>
              Status: {embedding?.status || 'unknown'}
              {embedding?.manifest?.revision ? ` — rev ${embedding.manifest.revision}` : ''}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              {(embedding?.status === 'missing' || embedding?.status === 'failed' || embedding?.status === 'canceled') && (
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
              {embedding?.status === 'installing' && (
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
              {embedding?.status === 'installed' && (
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
          </div>
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
