import React, { useEffect, useState } from 'react';
import { useAssetInstallMonitor } from '../../hooks/useAssetInstallMonitor';

interface AssetInstallBannerProps {
  assetId: string;
  assetName: string;
}

export const AssetInstallBanner: React.FC<AssetInstallBannerProps> = ({ assetId, assetName }) => {
  const { active, stage, message, percent } = useAssetInstallMonitor(assetId);
  const [overlayOpen, setOverlayOpen] = useState(false);

  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ open?: boolean }>;
      if (custom.detail && typeof custom.detail.open === 'boolean') {
        setOverlayOpen(custom.detail.open);
      }
    };
    document.addEventListener(`asset:overlay-visibility:${assetId}`, handler);
    return () => {
      document.removeEventListener(`asset:overlay-visibility:${assetId}`, handler);
    };
  }, [assetId]);

  if (!active || overlayOpen) return null;

  const pct = typeof percent === 'number' ? `${percent}%` : '';

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 18,
        left: '50%',
        transform: 'translateX(-50%)',
        maxWidth: 520,
        width: 'calc(100vw - 32px)',
        zIndex: 5200,
        padding: '8px 14px',
        borderRadius: 12,
        background: '#f4f1ea',
        border: '1px solid rgba(0, 0, 0, 0.08)',
        boxShadow: '0 20px 40px rgba(0, 0, 0, 0.3)',
        color: '#3a3a3a',
        fontSize: 13,
        display: 'flex',
        justifyContent: 'space-between',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
        <strong>Installing {assetName}</strong>
        <span style={{ fontSize: 11, color: '#6b7280' }}>
          {(message || stage || 'Working…') + (pct ? ` — ${pct}` : '')}
        </span>
      </div>
      <button
        onClick={() => {
          try {
            localStorage.removeItem(`asset:overlayDismissed:${assetId}`);
          } catch {
            // ignore
          }
          document.dispatchEvent(new Event(`asset:open-modal:${assetId}`));
        }}
        style={{
          background: '#e8e5de',
          border: '1px solid #d0cdc6',
          color: '#374151',
          padding: '2px 8px',
          borderRadius: 4,
          cursor: 'pointer',
        }}
      >
        View
      </button>
    </div>
  );
};
