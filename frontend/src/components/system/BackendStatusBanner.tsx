import React, { useEffect, useState } from 'react';
import { useBackendReadiness } from '../../hooks/useBackendReadiness';
import { ParcelTracerLoader } from '../image-processing/ParcelTracerLoader';

/**
 * Global backend readiness banner.
 *
 * Non-blocking, informational surface that lets users know when the
 * frozen backend is still booting on EXE startup and when it has become
 * healthy. Uses the last startup time as a rough estimate.
 */
export const BackendStatusBanner: React.FC = () => {
  const { ready, checking, estimateText } = useBackendReadiness();
  const [dismissed, setDismissed] = useState(false);
  const [visible, setVisible] = useState(true);

  // Restore session-level dismissal
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem('plattera:hideBackendBanner');
      if (raw === '1') {
        setDismissed(true);
        setVisible(false);
      }
    } catch {
      // ignore storage issues
    }
  }, []);

  // Keep showing briefly after ready, then auto-hide
  useEffect(() => {
    if (!ready) {
      if (!dismissed) {
        setVisible(true);
      }
      return;
    }
    if (dismissed) {
      setVisible(false);
      return;
    }
    setVisible(true);
    const t = setTimeout(() => {
      setVisible(false);
    }, 1800);
    return () => clearTimeout(t);
  }, [ready, dismissed]);

  const handleDismiss = () => {
    setDismissed(true);
    setVisible(false);
    try {
      sessionStorage.setItem('plattera:hideBackendBanner', '1');
    } catch {
      // ignore storage issues
    }
  };

  if (dismissed || !visible) return null;

  const dotColor = ready ? '#22c55e' : '#facc15';

  return (
    <div
      style={{
        position: 'fixed',
        top: 8,
        left: 8,
        right: 8,
        zIndex: 6000,
        padding: '6px 10px',
        borderRadius: 6,
        background: 'rgba(15, 23, 42, 0.95)',
        color: '#e5e7eb',
        fontSize: 12,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        pointerEvents: 'none', // non-blocking; inner controls re-enable
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {!ready && (
          <div style={{ width: 20, height: 20, pointerEvents: 'none' }}>
            <ParcelTracerLoader />
          </div>
        )}
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: dotColor,
          }}
        />
        <span>{estimateText || (ready ? 'Backend ready' : 'Starting backend…')}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        {!ready && (
          <span style={{ opacity: 0.7 }}>
            You can continue preparing workspaces while the backend finishes booting.
          </span>
        )}
        <div style={{ pointerEvents: 'auto' }}>
          <button
            onClick={handleDismiss}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#9ca3af',
              cursor: 'pointer',
              padding: 0,
              fontSize: 14,
              lineHeight: 1,
            }}
            title="Hide backend status"
          >
            ×
          </button>
        </div>
      </div>
    </div>
  );
};

