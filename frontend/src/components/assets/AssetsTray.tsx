import React, { useEffect, useRef, useState } from 'react';
import { assetsApi } from '../../services/assets/assetApi';
import { AssetRow } from '../../types/assets';
import { plssDataService } from '../../services/plss';
import { indexMaintenanceApi } from '../../services/retrieval/indexMaintenanceService';
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
      headline: row.headline ?? null,
      detail: row.detail ?? null,
      progress_bar: row.progress_bar ?? null,
      percent: typeof row.percent === 'number' ? row.percent : null,
      bytes_downloaded: typeof row.bytes_downloaded === 'number' ? row.bytes_downloaded : null,
      bytes_total: typeof row.bytes_total === 'number' ? row.bytes_total : null,
      current_file: row.current_file ?? null,
      phase: row.phase ?? null,
      updated_at: row.updated_at ?? null,
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
  const [purgeModalOpen, setPurgeModalOpen] = useState(false);
  const [purgeInProgress, setPurgeInProgress] = useState(false);
  const [purgeDone, setPurgeDone] = useState(false);
  const [purgeError, setPurgeError] = useState<string | null>(null);
  const [stopInProgress, setStopInProgress] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [cacheModalOpen, setCacheModalOpen] = useState(false);
  const [cacheInProgress, setCacheInProgress] = useState(false);
  const [cacheDone, setCacheDone] = useState(false);
  const [cacheError, setCacheError] = useState<string | null>(null);
  const bootstrapInFlightRef = useRef(false);
  const lastEmbeddingStatusRef = useRef<string | null>(null);
  const initialFetchDoneRef = useRef(false);
  const lastSnapshotRef = useRef<string | null>(null);

  useEffect(() => {
    if (!open) {
      initialFetchDoneRef.current = false;
      lastSnapshotRef.current = null;
      bootstrapInFlightRef.current = false;
      lastEmbeddingStatusRef.current = null;
      setLoading(false);
      return;
    }
    let cancelled = false;
    const poll = async () => {
      while (!cancelled) {
        // Only run fetch logic if we're still mounted and 'open' is true
        if (cancelled) break;

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
        
        // Wait before next loop, checking cancelled status
        if (!cancelled) {
          await new Promise(r => setTimeout(r, nextDelay));
        }
      }
    };
    poll();
    return () => {
      cancelled = true;
    };
  }, [open, plssState]);

  const embedding = assets.find(a => a.asset_id === EMBEDDING_ASSET_ID);
  const plss = assets.find(a => a.asset_id === 'plss');
  const plssInstalled = plss?.status === 'installed';
  const embeddingInstalled = embedding?.status === 'installed';
  const embeddingInstalling = embedding?.status === 'installing';
  const embeddingMissing =
    embedding?.status === 'missing' ||
    embedding?.status === 'failed' ||
    embedding?.status === 'canceled' ||
    embedding?.status === 'stopped' ||
    embedding?.status === 'stalled';

  useEffect(() => {
    if (!open) {
      return;
    }
    // Only run this logic if we have valid asset data and embedding object exists
    if (!embedding) return;

    const currentStatus = embedding.status;
    const previousStatus = lastEmbeddingStatusRef.current;
    
    // Always update the ref to current status
    if (currentStatus !== previousStatus) {
      lastEmbeddingStatusRef.current = currentStatus;
    }

    if (currentStatus !== 'installed') {
      bootstrapInFlightRef.current = false;
      return;
    }
    
    // Don't bootstrap if we were already installed or if a bootstrap is running
    if (previousStatus === 'installed' || bootstrapInFlightRef.current) {
      return;
    }
    
    bootstrapInFlightRef.current = true;
    indexMaintenanceApi.bootstrapIndex().catch((e) => {
      console.error('RAG bootstrap failed', e);
    });
  }, [open, embedding?.status, embedding?.asset_id]); // Added explicit dependencies to prevent churn

  const badgeStyles = (tone: 'good' | 'warn' | 'info' | 'danger') => {
    const palettes = {
      good: { bg: '#14532d', border: '#22c55e', text: '#dcfce7' },
      warn: { bg: '#78350f', border: '#f59e0b', text: '#fef3c7' },
      info: { bg: '#1e3a8a', border: '#60a5fa', text: '#dbeafe' },
      danger: { bg: '#7f1d1d', border: '#f87171', text: '#fee2e2' },
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
  const embeddingUpdateLabel = embedding?.updated_at
    ? new Date(embedding.updated_at).toLocaleTimeString()
    : null;
  const embeddingDetail = embedding?.detail || embedding?.message || embedding?.stage || null;

  const handleEmbeddingInstall = async () => {
    if (!embedding) return;
    setInstalling(true);
    try {
      await assetsApi.installAsset(embedding.asset_id);
      const list = await assetsApi.listAssets(plssState);
      const snapshot = buildSnapshot(list);
      if (snapshot !== lastSnapshotRef.current) {
        setAssets(list);
        lastSnapshotRef.current = snapshot;
      }
      try {
        localStorage.setItem(`asset:last:${embedding.asset_id}`, 'true');
        localStorage.removeItem(`asset:overlayDismissed:${embedding.asset_id}`);
      } catch {
        // ignore
      }
      try {
        document.dispatchEvent(new Event(`asset:open-modal:${embedding.asset_id}`));
      } catch (e) {
        console.error('Failed to dispatch asset:open-modal', e);
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

  const handleStopEmbedding = async () => {
    if (!embedding) return;
    try {
      setStopInProgress(true);
      await assetsApi.stop(embedding.asset_id);
      const list = await assetsApi.listAssets(plssState);
      const snapshot = buildSnapshot(list);
      if (snapshot !== lastSnapshotRef.current) {
        setAssets(list);
        lastSnapshotRef.current = snapshot;
      }
    } catch (e) {
      console.error('Stop failed', e);
    } finally {
      setStopInProgress(false);
    }
  };

  const handleClearCache = async () => {
    if (!embedding) return;
    try {
      setCacheInProgress(true);
      setCacheError(null);
      await assetsApi.clearCache(embedding.asset_id);
      setCacheDone(true);
    } catch (e) {
      setCacheError('Failed to clear cache.');
      console.error('Clear cache failed', e);
    } finally {
      setCacheInProgress(false);
    }
  };

  const handlePurgeEmbedding = async () => {
    if (!embedding) return;
    try {
      setPurgeInProgress(true);
      setPurgeError(null);
      await assetsApi.purge(embedding.asset_id);
      const list = await assetsApi.listAssets(plssState);
      const snapshot = buildSnapshot(list);
      if (snapshot !== lastSnapshotRef.current) {
        setAssets(list);
        lastSnapshotRef.current = snapshot;
      }
      setPurgeDone(true);
    } catch (e) {
      setPurgeError('Failed to purge embedding model.');
      console.error('Purge failed', e);
    } finally {
      setPurgeInProgress(false);
    }
  };

  if (!open) return null;

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
            ) : embedding?.status === 'failed' ? (
              <span style={badgeStyles('danger')}>Failed</span>
            ) : embedding?.status === 'stalled' ? (
              <span style={badgeStyles('danger')}>Stalled</span>
            ) : embedding?.status === 'stopped' ? (
              <span style={badgeStyles('warn')}>Stopped</span>
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
                onClick={handleStopEmbedding}
                disabled={stopInProgress}
                style={{
                  background: stopInProgress ? '#1f2937' : 'transparent',
                  color: '#f87171',
                  border: '1px solid #f87171',
                  padding: '6px 12px',
                  borderRadius: 6,
                  cursor: stopInProgress ? 'default' : 'pointer',
                }}
              >
                {stopInProgress ? 'Stopping...' : 'Stop'}
              </button>
            )}
          {embeddingInstalled && (
            <button
              onClick={() => {
                setPurgeModalOpen(true);
                setPurgeDone(false);
                setPurgeError(null);
              }}
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
            <div>{embeddingDetail}</div>
            {embeddingUpdateLabel && <div>Updated {embeddingUpdateLabel}</div>}
            <div>Stop ends the download and purges any partial files.</div>
          </div>
        )}
        {!embeddingInstalling && (
          <div style={{ marginTop: 10 }}>
            <button
              onClick={() => setAdvancedOpen(prev => !prev)}
              style={{
                background: 'transparent',
                border: '1px solid rgba(148, 163, 184, 0.4)',
                color: '#cbd5f5',
                padding: '4px 10px',
                borderRadius: 6,
                cursor: 'pointer',
                fontSize: 12,
              }}
            >
              {advancedOpen ? 'Hide advanced' : 'Advanced'}
            </button>
            {advancedOpen && (
              <div style={{ marginTop: 8 }}>
                <button
                  onClick={() => {
                    setCacheModalOpen(true);
                    setCacheDone(false);
                    setCacheError(null);
                  }}
                  style={{
                    background: 'transparent',
                    color: '#fca5a5',
                    border: '1px solid #fca5a5',
                    padding: '6px 12px',
                    borderRadius: 6,
                    cursor: 'pointer',
                  }}
                >
                  Clear cache
                </button>
              </div>
            )}
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

      {purgeModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(2, 6, 23, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2400,
          }}
          onClick={() => {
            if (!purgeInProgress) setPurgeModalOpen(false);
          }}
        >
          <div
            style={{
              background: '#0f172a',
              color: '#f8fafc',
              padding: 22,
              borderRadius: 12,
              width: 420,
              border: '1px solid rgba(148, 163, 184, 0.2)',
              boxShadow: '0 24px 60px rgba(0,0,0,0.45)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <style>{`
              @keyframes purge-spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
              }
            `}</style>
            <h3 style={{ marginTop: 0, marginBottom: 8 }}>Purge embedding model</h3>
            {!purgeInProgress && !purgeDone && (
              <p style={{ marginTop: 0, color: '#cbd5f5' }}>
                This removes the downloaded model files from disk. You can reinstall later.
              </p>
            )}
            {purgeInProgress && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: '#cbd5f5' }}>
                <div
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: '50%',
                    border: '2px solid rgba(226,232,240,0.4)',
                    borderTopColor: '#38bdf8',
                    animation: 'purge-spin 1s linear infinite',
                  }}
                />
                <span>Purging embedding model...</span>
              </div>
            )}
            {purgeDone && !purgeInProgress && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: '#bbf7d0' }}>
                <div
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: 4,
                    background: '#16a34a',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    color: '#052e16',
                    fontWeight: 700,
                  }}
                >
                  ✓
                </div>
                <span>Purge complete.</span>
              </div>
            )}
            {purgeError && (
              <div style={{ marginTop: 10, color: '#fca5a5', fontSize: 12 }}>{purgeError}</div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
              {!purgeInProgress && !purgeDone && (
                <>
                  <button
                    onClick={() => setPurgeModalOpen(false)}
                    style={{
                      padding: '8px 14px',
                      background: 'transparent',
                      color: '#e2e8f0',
                      border: '1px solid rgba(148, 163, 184, 0.4)',
                      borderRadius: 6,
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handlePurgeEmbedding}
                    style={{
                      padding: '8px 14px',
                      background: '#b45309',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 6,
                      cursor: 'pointer',
                    }}
                  >
                    Purge
                  </button>
                </>
              )}
              {purgeDone && !purgeInProgress && (
                <button
                  onClick={() => setPurgeModalOpen(false)}
                  style={{
                    padding: '8px 14px',
                    background: '#16a34a',
                    color: '#052e16',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Done
                </button>
              )}
              {purgeInProgress && (
                <button
                  disabled
                  style={{
                    padding: '8px 14px',
                    background: '#1f2937',
                    color: '#94a3b8',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'default',
                  }}
                >
                  Working...
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {cacheModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(2, 6, 23, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 2400,
          }}
          onClick={() => {
            if (!cacheInProgress) setCacheModalOpen(false);
          }}
        >
          <div
            style={{
              background: '#0f172a',
              color: '#f8fafc',
              padding: 22,
              borderRadius: 12,
              width: 430,
              border: '1px solid rgba(148, 163, 184, 0.2)',
              boxShadow: '0 24px 60px rgba(0,0,0,0.45)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <style>{`
              @keyframes cache-spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
              }
            `}</style>
            <h3 style={{ marginTop: 0, marginBottom: 8 }}>Clear embedding cache</h3>
            {!cacheInProgress && !cacheDone && (
              <p style={{ marginTop: 0, color: '#cbd5f5' }}>
                This removes the local HF cache and forces a full redownload next install.
              </p>
            )}
            {cacheInProgress && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: '#cbd5f5' }}>
                <div
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: '50%',
                    border: '2px solid rgba(226,232,240,0.4)',
                    borderTopColor: '#38bdf8',
                    animation: 'cache-spin 1s linear infinite',
                  }}
                />
                <span>Clearing cache...</span>
              </div>
            )}
            {cacheDone && !cacheInProgress && (
              <div style={{ display: 'flex', gap: 10, alignItems: 'center', color: '#bbf7d0' }}>
                <div
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: 4,
                    background: '#16a34a',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    color: '#052e16',
                    fontWeight: 700,
                  }}
                >
                  ✓
                </div>
                <span>Cache cleared.</span>
              </div>
            )}
            {cacheError && (
              <div style={{ marginTop: 10, color: '#fca5a5', fontSize: 12 }}>{cacheError}</div>
            )}

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 18 }}>
              {!cacheInProgress && !cacheDone && (
                <>
                  <button
                    onClick={() => setCacheModalOpen(false)}
                    style={{
                      padding: '8px 14px',
                      background: 'transparent',
                      color: '#e2e8f0',
                      border: '1px solid rgba(148, 163, 184, 0.4)',
                      borderRadius: 6,
                      cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleClearCache}
                    style={{
                      padding: '8px 14px',
                      background: '#b91c1c',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 6,
                      cursor: 'pointer',
                    }}
                  >
                    Clear cache
                  </button>
                </>
              )}
              {cacheDone && !cacheInProgress && (
                <button
                  onClick={() => setCacheModalOpen(false)}
                  style={{
                    padding: '8px 14px',
                    background: '#16a34a',
                    color: '#052e16',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  Done
                </button>
              )}
              {cacheInProgress && (
                <button
                  disabled
                  style={{
                    padding: '8px 14px',
                    background: '#1f2937',
                    color: '#94a3b8',
                    border: 'none',
                    borderRadius: 6,
                    cursor: 'default',
                  }}
                >
                  Working...
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
