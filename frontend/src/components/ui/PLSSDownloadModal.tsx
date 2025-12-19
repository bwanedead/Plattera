import React from 'react';
import { createPortal } from 'react-dom';

interface PLSSDownloadModalProps {
  isOpen: boolean;
  state: string;
  onDownload?: () => void;
  onCancel: () => void;
  isDownloading: boolean;
  progressText?: string | null;
  onHardCancel?: () => void;
  // Optional enhanced feedback for parquet finalization
  parquetPhase?: boolean;
  parquetStatus?: string | null;
  estimatedTime?: string | null;
  // Structured progress (preferred over parsing progressText)
  progressPercent?: number | null;
  progressBar?: 'determinate' | 'indeterminate' | 'none';
  progressHeadline?: string | null;
  progressDetail?: string | null;
  progressRawStage?: string | null;
}

/**
 * PLSS Download Confirmation Modal
 *
 * Clean, minimal modal for PLSS data download confirmation.
 */
export const PLSSDownloadModal: React.FC<PLSSDownloadModalProps> = ({
  isOpen,
  state,
  onDownload,
  onCancel,
  isDownloading,
  progressText,
  onHardCancel,
  parquetPhase,
  parquetStatus,
  estimatedTime,
  progressPercent,
  progressBar,
  progressHeadline,
  progressDetail,
  progressRawStage,
}) => {
  if (!isOpen) return null;

  // Dismiss-only handler: closes the modal without affecting the backend job.
  const handleDismiss = () => {
    try {
      onCancel();
    } catch (e) {
      console.error('Error in PLSS onCancel handler', e);
    }
  };

  // Hard cancel handler: explicitly stops the download (if supported) and then dismisses.
  const handleHardCancel = () => {
    if (onHardCancel) {
      try {
        onHardCancel();
      } catch (e) {
        console.error('Error during PLSS hard cancel', e);
      }
    }

    try {
      onCancel();
    } catch (e) {
      console.error('Error in PLSS onCancel handler', e);
    }
  };

  const effectiveProgressBar: 'determinate' | 'indeterminate' | 'none' =
    progressBar || (isDownloading ? 'indeterminate' : 'none');

  const computeWidth = () => {
    if (effectiveProgressBar === 'determinate' && typeof progressPercent === 'number') {
      const clamped = Math.max(0, Math.min(progressPercent, 100));
      return `${clamped}%`;
    }
    return effectiveProgressBar === 'indeterminate' ? '40%' : '0%';
  };

  const parquetDetail =
    progressDetail ||
    parquetStatus ||
    progressRawStage ||
    'Building high-performance parquet files for: Townships, Sections, Quarter Sections.';

  return createPortal(
    <div className="plss-modal-overlay" onClick={handleDismiss}>
      <div className="plss-modal-content" onClick={(e) => e.stopPropagation()}>
        {parquetPhase ? (
          <div className="plss-modal-message">
            <p>
              {progressHeadline ? (
                progressHeadline
              ) : (
                <>
                  🔧 Finalizing PLSS data for <strong>{state}</strong>.
                </>
              )}
            </p>
            <p className="plss-modal-details">{parquetDetail}</p>

            {/* Progress bar for parquet building / finalization */}
            <div className="plss-progress-bar" style={{ marginTop: 12 }}>
              <div
                className="plss-progress-track"
                style={{ height: 6, background: '#222', borderRadius: 4 }}
              >
                <div
                  className="plss-progress-fill"
                  style={{
                    height: 6,
                    width: computeWidth(),
                    background: 'linear-gradient(90deg, #6ee7ff, #7c3aed)',
                    borderRadius: 4,
                    transition: 'width 300ms ease',
                  }}
                />
              </div>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: 11,
                  color: '#aaa',
                  marginTop: 6,
                }}
              >
                <span>{parquetDetail}</span>
                <span>Est: {estimatedTime || '15-20 minutes'}</span>
              </div>
            </div>
          </div>
        ) : isDownloading ? (
          <div className="plss-modal-message">
            <p>
              {progressHeadline ? (
                progressHeadline
              ) : (
                <>
                  Downloading PLSS data for <strong>{state}</strong>…
                </>
              )}
            </p>
            <p className="plss-modal-details">
              This may take several minutes. You can cancel if needed; a future download will start
              from a clean state.
            </p>
          </div>
        ) : (
          <div className="plss-modal-message">
            <p>
              Need to download PLSS data for <strong>{state}</strong> from BLM.
            </p>
            <p className="plss-modal-details">
              This will download Wyoming PLSS bulk data (Townships, Sections, Subdivisions) for
              offline use. Download size: ~252 MB; Installed size: ~484 MB on disk after install.
            </p>
          </div>
        )}

        <div className="plss-modal-actions">
          <button className="plss-btn plss-btn-cancel" onClick={handleDismiss}>
            Close
          </button>
          <button
            className="plss-btn plss-btn-download"
            onClick={onDownload}
            disabled={isDownloading || !onDownload}
          >
            {isDownloading ? (
              <>
                <div className="plss-spinner"></div>
                {progressHeadline || progressText || 'Downloading...'}
              </>
            ) : (
              'Download'
            )}
          </button>
        </div>

        {isDownloading && !parquetPhase && (
          <div className="plss-progress-bar" style={{ marginTop: 12 }}>
            <div
              className="plss-progress-track"
              style={{ height: 6, background: '#222', borderRadius: 4 }}
            >
              <div
                className="plss-progress-fill"
                style={{
                  height: 6,
                  width: computeWidth(),
                  background: 'linear-gradient(90deg, #6ee7ff, #7c3aed)',
                  borderRadius: 4,
                  transition: 'width 300ms ease',
                }}
              />
            </div>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                fontSize: 11,
                color: '#aaa',
                marginTop: 6,
              }}
            >
              <span>{progressHeadline || progressText || 'Preparing...'}</span>
              {onHardCancel && (
                <button
                  className="plss-btn small"
                  onClick={handleHardCancel}
                  style={{ background: 'transparent', color: '#bbb' }}
                >
                  Stop
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
};

