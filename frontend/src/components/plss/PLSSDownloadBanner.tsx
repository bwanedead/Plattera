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
  const { active, state, stage, percent, text } = usePlssDownloadMonitor();

  if (!active || !state) return null;

  const label = text || stage || 'Downloading PLSS data...';
  const pct = typeof percent === 'number' ? `${percent}%` : '';

  const handleStop = async () => {
    try {
      await plssDataService.cancelDownload(state);
    } catch (e) {
      console.error('PLSS banner stop failed', e);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 8,
        left: 8,
        right: 8,
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
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#38bdf8',
          }}
        />
        <span>
          Downloading PLSS for <strong>{state}</strong>
          {pct && <> — {pct}</>}
        </span>
        {label && <span style={{ opacity: 0.8 }}>({label})</span>}
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
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

