import React from 'react';
import { createPortal } from 'react-dom';

interface PLSSDownloadModalProps {
  isOpen: boolean;
  state: string;
  onDownload: () => void;
  onCancel: () => void;
  isDownloading: boolean;
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
  isDownloading
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
            One-time download, stored locally for future use.
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
                Downloading...
              </>
            ) : (
              'Download'
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};