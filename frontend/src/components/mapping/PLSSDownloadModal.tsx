import React from 'react';
import { createPortal } from 'react-dom';

interface PLSSDownloadModalProps {
  isOpen: boolean;
  state: string;
  onDownload: () => void;
  onCancel: () => void;
  isDownloading: boolean;
}

export const PLSSDownloadModal: React.FC<PLSSDownloadModalProps> = ({
  isOpen,
  state,
  onDownload,
  onCancel,
  isDownloading
}) => {
  if (!isOpen) return null;

  // Render modal at document root level using portal
  return createPortal(
    <div className="modal-overlay" onClick={onCancel}>
      <div className="modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Download Required</h2>
          <button className="modal-close" onClick={onCancel} aria-label="Close">
            ×
          </button>
        </div>
        
        <div className="modal-body">
          <p>
            To display the map for <strong>{state}</strong>, we need to download 
            Public Land Survey System (PLSS) data from the Bureau of Land Management.
          </p>
          
          <div className="download-info">
            <h3>What will be downloaded:</h3>
            <ul>
              <li>Official PLSS township and section boundaries</li>
              <li>Survey grid data for accurate mapping</li>
              <li>Approximately 2-10MB of vector data</li>
              <li>One-time download, stored locally</li>
            </ul>
            
            <div className="data-source">
              <strong>Data Source:</strong> Bureau of Land Management (BLM) - Official Government Data
            </div>
          </div>
          
          <p>
            This is a <strong>one-time download</strong> that will be stored in your 
            project directory for future use.
          </p>
        </div>
        
        <div className="modal-footer">
          <button 
            className="btn-cancel" 
            onClick={onCancel}
            disabled={isDownloading}
          >
            Cancel
          </button>
          <button 
            className="btn-download" 
            onClick={onDownload}
            disabled={isDownloading}
          >
            {isDownloading ? (
              <>
                <div className="spinner"></div>
                Downloading...
              </>
            ) : (
              'Download PLSS Data'
            )}
          </button>
        </div>
      </div>
    </div>,
    document.body // Render at document body level
  );
};
