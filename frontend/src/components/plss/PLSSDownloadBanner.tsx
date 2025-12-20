import React from 'react';
import { usePlssDownloadMonitor } from '../../hooks/usePlssDownloadMonitor';
import { plssDataService } from '../../services/plss';

/**
 * Global, non-blocking PLSS download status banner.
 * 
 * Shows at the bottom of the app whenever a background PLSS download is
 * in progress, so users can keep working while being aware of the job.
 */
export const PLSSDownloadBanner: React.FC = () => {
  const { active, state, ui } = usePlssDownloadMonitor();

  if (!active || !state || !ui) return null;

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
        padding: '6px 10px',
        borderRadius: 6,
        background: 'rgba(15, 23, 42, 0.9)',
        color: '#e5e7eb',
        fontSize: 12,
        pointerEvents: 'auto',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#38bdf8',
          }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          {/* Primary line: stage + percent, never ellipsized */}
          <div style={{ whiteSpace: 'nowrap' }}>
            {ui.headline || 'Downloading PLSS data…'} for <strong>{state}</strong>
            {pct && <> — {pct}</>}
          </div>
          {/* Secondary line: detail/status, ellipsized if long */}
          {label && (
            <div
              style={{
                fontSize: 11,
                color: '#9ca3af',
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
            background: 'transparent',
            border: '1px solid #38bdf8',
            color: '#e0f2fe',
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
            border: '1px solid #f97373',
            color: '#fecaca',
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

