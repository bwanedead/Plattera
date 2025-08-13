import React from 'react';
import { createPortal } from 'react-dom';

interface PLSSDownloadModalProps {
  isOpen: boolean;
  state: string;
  onDownload: () => void;
  onCancel: () => void;
  isDownloading: boolean;
  progressText?: string | null;
  onHardCancel?: () => void;
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
  onHardCancel
}) => {
  if (!isOpen) return null;

  return createPortal(
    <div className="plss-modal-overlay" onClick={onCancel}>
      <div className="plss-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="plss-modal-message">
          <p>
            Need to download PLSS data for <strong>{state}</strong> from BLM.
          </p>
          <p className="plss-modal-details">
            This will download Wyoming PLSS bulk data (Townships, Sections, Subdivisions) for offline use.
            Download size: ~252 MB; Installed size: ~484 MB on disk after install.
          </p>
        </div>
        
        <div className="plss-modal-actions">
          <button 
            className="plss-btn plss-btn-cancel" 
            onClick={onCancel}
            disabled={isDownloading}
          >
            Cancel
          </button>
          <button 
            className="plss-btn plss-btn-download" 
            onClick={onDownload}
            disabled={isDownloading}
          >
            {isDownloading ? (
              <>
                <div className="plss-spinner"></div>
                {progressText || 'Downloading...'}
              </>
            ) : (
              'Download'
            )}
          </button>
        </div>

        {isDownloading && (
          <div className="plss-progress-bar" style={{ marginTop: 12 }}>
            <div className="plss-progress-track" style={{ height: 6, background: '#222', borderRadius: 4 }}>
              <div
                className="plss-progress-fill"
                style={{
                  height: 6,
                  width: `${(() => {
                    const m = /([0-9]{1,3})%/.exec(progressText || '')?.[1];
                    const p = m ? parseInt(m, 10) : 0;
                    return Math.max(0, Math.min(p, 100));
                  })()}%`,
                  background: 'linear-gradient(90deg, #6ee7ff, #7c3aed)',
                  borderRadius: 4,
                  transition: 'width 300ms ease'
                }}
              />
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: '#aaa', marginTop: 6 }}>
              <span>{progressText || 'Preparing...'}</span>
              {onHardCancel && (
                <button className="plss-btn small" onClick={onHardCancel} style={{ background: 'transparent', color: '#bbb' }}>
                  Stop
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body
  );
};