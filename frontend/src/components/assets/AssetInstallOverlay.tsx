import React, { useEffect, useState } from 'react';
import { useAssetInstallMonitor } from '../../hooks/useAssetInstallMonitor';
import { assetsApi } from '../../services/assets/assetApi';

interface AssetInstallOverlayProps {
  assetId: string;
  assetName: string;
}

export const AssetInstallOverlay: React.FC<AssetInstallOverlayProps> = ({ assetId, assetName }) => {
  const {
    active,
    status,
    stage,
    message,
    headline,
    detail,
    progressBar,
    percent,
    bytesDownloaded,
    bytesTotal,
    updatedAt,
    elapsedSeconds,
  } = useAssetInstallMonitor(assetId);
  const [dismissed, setDismissed] = useState(false);
  const [forceOpen, setForceOpen] = useState(false);
  const [stopInProgress, setStopInProgress] = useState(false);
  const [stopDone, setStopDone] = useState(false);

  useEffect(() => {
    const key = `asset:overlayDismissed:${assetId}`;
    try {
      const stored = localStorage.getItem(key);
      setDismissed(stored === 'true');
    } catch {
      setDismissed(false);
    }
  }, [assetId]);

  useEffect(() => {
    const eventName = `asset:open-modal:${assetId}`;
    const handler = () => {
      try {
        localStorage.removeItem(`asset:overlayDismissed:${assetId}`);
      } catch {
        // ignore storage errors
      }
      setDismissed(false);
      setForceOpen(true);
      setTimeout(() => {
        setForceOpen(prev => (active ? prev : false));
      }, 8000);
    };
    document.addEventListener(eventName, handler);
    return () => {
      document.removeEventListener(eventName, handler);
    };
  }, [assetId, active]);

  useEffect(() => {
    if (active) {
      setForceOpen(false);
      setStopDone(false);
    }
  }, [active]);

  useEffect(() => {
    if (status && status !== 'installing') {
      setForceOpen(false);
      setStopInProgress(false);
    }
  }, [status]);

  useEffect(() => {
    const event = new CustomEvent(`asset:overlay-visibility:${assetId}`, {
      detail: { open: (active || forceOpen) && !dismissed },
    });
    document.dispatchEvent(event);
  }, [assetId, active, dismissed, forceOpen]);

  if ((!active && !forceOpen) || dismissed) return null;

  const pct = typeof percent === 'number' ? `${percent}%` : '';
  const headlineText = headline || `Installing ${assetName}`;
  const detailText = detail || message || stage || 'Starting download...';
  const stageText = stage ? `Stage: ${stage}` : null;
  const elapsedLabel = typeof elapsedSeconds === 'number'
    ? `${Math.floor(elapsedSeconds / 60)}:${String(elapsedSeconds % 60).padStart(2, '0')}`
    : null;
  const showDeterminate =
    (progressBar === 'determinate' && typeof percent === 'number') ||
    (!progressBar && typeof percent === 'number');
  const formatBytes = (value: number) => {
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let size = value;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex += 1;
    }
    return `${size.toFixed(1)} ${units[unitIndex]}`;
  };

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 2400,
      }}
    >
      <div
        style={{
          background: '#0f172a',
          color: '#f8fafc',
          padding: 24,
          borderRadius: 12,
          width: 460,
          boxShadow: '0 30px 60px rgba(0,0,0,0.5)',
        }}
      >
        <style>{`
          @keyframes asset-indeterminate {
            0% { transform: translateX(-60%); }
            100% { transform: translateX(160%); }
          }
        `}</style>
        <h3 style={{ margin: 0 }}>{stopInProgress ? 'Stopping download' : headlineText}</h3>
        <p style={{ color: '#cbd5f5', marginTop: 8, marginBottom: 6 }}>
          {stopInProgress ? 'Terminating download process and purging files.' : detailText}
        </p>
        {!stopInProgress && stageText && <div style={{ color: '#94a3b8', fontSize: 12 }}>{stageText}</div>}

        {!stopInProgress && (
          <div style={{ marginTop: 14 }}>
          {showDeterminate ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div
                style={{
                  height: 8,
                  borderRadius: 999,
                  background: '#1e293b',
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${Math.min(100, Math.max(0, percent || 0))}%`,
                    height: '100%',
                    background: 'linear-gradient(90deg, #38bdf8, #60a5fa)',
                    transition: 'width 0.4s ease',
                  }}
                />
              </div>
                <div style={{ fontSize: 12, color: '#cbd5f5' }}>
                  {pct}
                  {bytesDownloaded && bytesTotal
                    ? ` · ${formatBytes(bytesDownloaded)} / ${formatBytes(bytesTotal)}`
                    : ''}
                </div>
              </div>
            ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <div
                style={{
                  height: 8,
                  borderRadius: 999,
                  background: '#1e293b',
                  overflow: 'hidden',
                  position: 'relative',
                }}
              >
                <div
                  style={{
                    position: 'absolute',
                    left: 0,
                    top: 0,
                    height: '100%',
                    width: '40%',
                    background: 'linear-gradient(90deg, rgba(56,189,248,0.0), rgba(56,189,248,0.9), rgba(56,189,248,0.0))',
                    animation: 'asset-indeterminate 1.4s ease-in-out infinite',
                  }}
                />
              </div>
              <div style={{ fontSize: 12, color: '#cbd5f5' }}>
                Downloading...
              </div>
            </div>
          )}
          </div>
        )}

        {stopInProgress && (
          <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 10, color: '#cbd5f5' }}>
            <div
              style={{
                width: 18,
                height: 18,
                borderRadius: '50%',
                border: '2px solid rgba(226,232,240,0.4)',
                borderTopColor: '#38bdf8',
                animation: 'asset-indeterminate 1s linear infinite',
              }}
            />
            <span>Stopping and cleaning up...</span>
          </div>
        )}

        {stopDone && !active && (
          <div style={{ marginTop: 16, display: 'flex', alignItems: 'center', gap: 10, color: '#bbf7d0' }}>
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
            <span>Download stopped and cleaned.</span>
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 14, fontSize: 11, color: '#94a3b8' }}>
          <span>{elapsedLabel ? `Elapsed ${elapsedLabel}` : ''}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <button
            onClick={async () => {
              try {
                setStopInProgress(true);
                setStopDone(false);
                await assetsApi.stop(assetId);
                setStopDone(true);
              } catch (e) {
                console.error('Stop failed', e);
              } finally {
                setStopInProgress(false);
              }
            }}
            disabled={stopInProgress || stopDone}
            style={{
              background: stopInProgress || stopDone ? '#1f2937' : 'transparent',
              border: '1px solid #f87171',
              color: '#f87171',
              padding: '6px 12px',
              borderRadius: 6,
              cursor: stopInProgress || stopDone ? 'default' : 'pointer',
              fontSize: 12,
            }}
          >
            {stopInProgress ? 'Stopping...' : stopDone ? 'Stopped' : 'Stop'}
          </button>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>
            Stop ends the download and purges any partial files.
          </span>
          <button
            onClick={() => {
              try {
                localStorage.setItem(`asset:overlayDismissed:${assetId}`, 'true');
              } catch {
                // ignore storage errors
              }
              setDismissed(true);
              setForceOpen(false);
              setStopDone(false);
            }}
            style={{
              background: 'transparent',
              border: '1px solid rgba(148, 163, 184, 0.4)',
              color: '#e2e8f0',
              padding: '6px 12px',
              borderRadius: 6,
              cursor: 'pointer',
            }}
          >
            Dismiss
          </button>
        </div>
      </div>
    </div>
  );
};
