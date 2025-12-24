import React, { useEffect, useState } from 'react';
import { usePlssDownloadMonitor } from '../../hooks/usePlssDownloadMonitor';
import { plssDataService } from '../../services/plss';

/**
 * Global, non-blocking PLSS download status banner.
 * 
 * Shows at the bottom of the app whenever a background PLSS download is
 * in progress, so users can keep working while being aware of the job.
 */
export const PLSSDownloadBanner: React.FC = () => {
  const [overlayOpen, setOverlayOpen] = useState(false);
  const { active, state, ui } = usePlssDownloadMonitor();

  // Listen for overlay visibility events so the banner can hide whenever the
  // detailed progress modal is open. This keeps the experience "either/or"
  // instead of stacking the banner behind the modal.
  useEffect(() => {
    const handler = (event: Event) => {
      const custom = event as CustomEvent<{ open?: boolean }>;
      if (custom.detail && typeof custom.detail.open === 'boolean') {
        setOverlayOpen(custom.detail.open);
      }
    };

    document.addEventListener('plss:overlay-visibility', handler);
    return () => {
      document.removeEventListener('plss:overlay-visibility', handler);
    };
  }, []);

  if (!active || !state || !ui || overlayOpen) return null;

  const label = ui.detail || ui.rawStage || 'Downloading PLSS data...';
  const pct = ui.showPercent && typeof ui.percent === 'number' ? `${ui.percent}%` : '';

  const handleStop = async () => {
    try {
      await plssDataService.cancelDownload(state);
    } catch (e) {
      console.error('PLSS banner stop failed', e);
    }
  };

  const handleView = () => {
    try {
      document.dispatchEvent(new Event('plss:open-modal'));
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('Failed to dispatch plss:open-modal event', e);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        maxWidth: 520,
        width: 'calc(100vw - 32px)',
        zIndex: 5000,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 14px',
        borderRadius: 12,
        background: '#f4f1ea',
        border: '1px solid rgba(0, 0, 0, 0.08)',
        boxShadow: '0 20px 40px rgba(0, 0, 0, 0.3)',
        color: '#3a3a3a',
        fontSize: 13,
        pointerEvents: 'auto',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1, minWidth: 0 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <span
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: '#22c55e',
            }}
          />
          <div
            className="plss-spinner"
            style={{
              border: '2px solid rgba(148, 163, 184, 0.4)',
              borderTopColor: '#22c55e',
            }}
          />
        </span>
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {/* Primary line: stage + percent, never ellipsized */}
          <div
            style={{
              whiteSpace: 'nowrap',
              fontWeight: 600,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
          >
            {ui.headline || 'Downloading PLSS data…'} for <strong>{state}</strong>
            {pct && <> — {pct}</>}
          </div>
          {/* Secondary line: detail/status, ellipsized if long */}
          {label && (
            <div
              style={{
                fontSize: 11,
                color: '#6b7280',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                marginTop: 2,
              }}
            >
              {label}
            </div>
          )}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8, marginLeft: 8 }}>
        <button
          className="plss-btn small"
          onClick={handleView}
          style={{
            background: '#e8e5de',
            border: '1px solid #d0cdc6',
            color: '#374151',
            padding: '2px 8px',
            borderRadius: 4,
            cursor: 'pointer',
          }}
          title="View detailed PLSS download progress"
        >
          View
        </button>
        <button
          className="plss-btn small"
          onClick={handleStop}
          style={{
            background: 'transparent',
            border: '1px solid #fca5a5',
            color: '#b91c1c',
            padding: '2px 8px',
            borderRadius: 4,
            cursor: 'pointer',
          }}
          title="Stop PLSS download"
        >
          Stop
        </button>
      </div>
    </div>
  );
};

