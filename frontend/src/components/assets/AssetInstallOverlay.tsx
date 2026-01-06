import React, { useEffect, useState } from 'react';
import { useAssetInstallMonitor } from '../../hooks/useAssetInstallMonitor';

interface AssetInstallOverlayProps {
  assetId: string;
  assetName: string;
}

export const AssetInstallOverlay: React.FC<AssetInstallOverlayProps> = ({ assetId, assetName }) => {
  const {
    active,
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
    };
    document.addEventListener(eventName, handler);
    return () => {
      document.removeEventListener(eventName, handler);
    };
  }, [assetId]);

  useEffect(() => {
    const event = new CustomEvent(`asset:overlay-visibility:${assetId}`, {
      detail: { open: active && !dismissed },
    });
    document.dispatchEvent(event);
  }, [assetId, active, dismissed]);

  if (!active || dismissed) return null;

  const pct = typeof percent === 'number' ? `${percent}%` : '';
  const headlineText = headline || `Installing ${assetName}`;
  const detailText = detail || message || stage || 'Working...';
  const stageText = stage ? `Stage: ${stage}` : null;
  const updatedLabel = updatedAt ? new Date(updatedAt).toLocaleTimeString() : null;
  const elapsedLabel = typeof elapsedSeconds === 'number'
    ? `${Math.floor(elapsedSeconds / 60)}:${String(elapsedSeconds % 60).padStart(2, '0')}`
    : null;
  const showDeterminate =
    (progressBar === 'determinate' && typeof percent === 'number') ||
    (!progressBar && typeof percent === 'number');

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
        <h3 style={{ margin: 0 }}>{headlineText}</h3>
        <p style={{ color: '#cbd5f5', marginTop: 8, marginBottom: 6 }}>{detailText}</p>
        {stageText && <div style={{ color: '#94a3b8', fontSize: 12 }}>{stageText}</div>}

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
                {bytesDownloaded && bytesTotal ? ` · ${bytesDownloaded.toLocaleString()} / ${bytesTotal.toLocaleString()} bytes` : ''}
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

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 14, fontSize: 11, color: '#94a3b8' }}>
          <span>{elapsedLabel ? `Elapsed ${elapsedLabel}` : ''}</span>
          <span>{updatedLabel ? `Updated ${updatedLabel}` : ''}</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 }}>
          <span style={{ fontSize: 11, color: '#94a3b8' }}>
            Cancel stops after the current download step completes.
          </span>
          <button
            onClick={() => {
              try {
                localStorage.setItem(`asset:overlayDismissed:${assetId}`, 'true');
              } catch {
                // ignore storage errors
              }
              setDismissed(true);
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
