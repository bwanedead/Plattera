import React, { useEffect, useState } from 'react';
import { useAssetInstallMonitor } from '../../hooks/useAssetInstallMonitor';

interface AssetInstallOverlayProps {
  assetId: string;
  assetName: string;
}

export const AssetInstallOverlay: React.FC<AssetInstallOverlayProps> = ({ assetId, assetName }) => {
  const { active, stage, message, percent } = useAssetInstallMonitor(assetId);
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

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1050,
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
        <h3 style={{ margin: 0 }}>Installing {assetName}</h3>
        <p style={{ color: '#cbd5f5', marginTop: 8 }}>
          {message || stage || 'Working…'} {pct}
        </p>
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 16 }}>
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
