import React, { useEffect, useState } from 'react';
import { usePlssDownloadMonitor } from '../../hooks/usePlssDownloadMonitor';
import { plssDataService } from '../../services/plss';
import { PLSSDownloadModal } from '../ui';

/**
 * Global PLSS download overlay.
 *
 * - Listens to the shared usePlssDownloadMonitor() hook so there is a single
 *   source of truth for backend‑reported progress.
 * - Opens automatically when a download is active unless the user has
 *   explicitly dismissed it for the current state.
 * - Can also be explicitly opened by dispatching a `plss:open-modal` event
 *   on document (used by the banner "View" button).
 */
export const PLSSDownloadOverlay: React.FC = () => {
  const { active, state, ui } = usePlssDownloadMonitor();
  const [isOpen, setIsOpen] = useState(false);

  const isProgressPhase =
    !!ui &&
    (ui.phase === 'downloading' ||
      ui.phase === 'building_parquet' ||
      ui.phase === 'finalizing');

  // Track per‑state dismissal in localStorage so we don't re‑open the overlay
  // every time the user navigates while a long download is running.
  useEffect(() => {
    if (!active || !state || !ui || !isProgressPhase) {
      setIsOpen(false);
      return;
    }

    try {
      const key = `plss:overlayDismissed:${state}`;
      const dismissed = localStorage.getItem(key) === 'true';
      if (!dismissed) {
        setIsOpen(true);
      }
    } catch {
      setIsOpen(true);
    }
  }, [active, state, ui, isProgressPhase]);

  // Broadcast overlay visibility so other UI elements (like the banner) can
  // hide while the modal is open. This keeps ownership of "progress UI"
  // single and avoids stacking the banner behind the overlay.
  useEffect(() => {
    try {
      const event = new CustomEvent('plss:overlay-visibility', {
        detail: { open: isOpen },
      });
      document.dispatchEvent(event);
    } catch {
      // Ignore environments without CustomEvent (unlikely in Tauri/WebView).
    }
  }, [isOpen]);

  // Allow other components (e.g. the banner) to explicitly open the overlay.
  useEffect(() => {
    const handler = () => {
      if (!state) return;
      setIsOpen(true);
      try {
        const key = `plss:overlayDismissed:${state}`;
        localStorage.removeItem(key);
      } catch {
        // ignore storage errors
      }
    };

    document.addEventListener('plss:open-modal', handler);
    return () => {
      document.removeEventListener('plss:open-modal', handler);
    };
  }, [state]);

  const handleCancel = () => {
    setIsOpen(false);
    if (!state) return;
    try {
      const key = `plss:overlayDismissed:${state}`;
      localStorage.setItem(key, 'true');
    } catch {
      // ignore storage errors
    }
  };

  const handleHardCancel = async () => {
    if (!state) return;
    try {
      await plssDataService.cancelDownload(state);
    } catch (e) {
      // eslint-disable-next-line no-console
      console.error('PLSS overlay hard cancel failed', e);
    }
  };

  if (!active || !state || !ui || !isProgressPhase) return null;

  const parquetPhase =
    ui.phase === 'building_parquet' || ui.phase === 'finalizing';

  return (
    <PLSSDownloadModal
      isOpen={isOpen}
      state={state}
      // Progress‑only overlay – Download action lives in the mapping view.
      onDownload={undefined}
      onCancel={handleCancel}
      isDownloading={true}
      progressText={ui.detail || ui.rawStage || null}
      onHardCancel={handleHardCancel}
      parquetPhase={parquetPhase}
      parquetStatus={ui.detail || null}
      estimatedTime={null}
      progressPercent={ui.percent ?? null}
      progressBar={ui.progressBar}
      progressHeadline={ui.headline}
      progressDetail={ui.detail ?? null}
      progressRawStage={ui.rawStage ?? null}
    />
  );
};

