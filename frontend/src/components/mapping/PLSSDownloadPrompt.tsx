/**
 * PLSS Download Prompt - Pure UI component
 * Only handles presentation, no business logic
 */
import React from 'react';

interface PLSSDownloadPromptProps {
  state: string;
  onDownload: () => void;
}

export const PLSSDownloadPrompt: React.FC<PLSSDownloadPromptProps> = ({
  state,
  onDownload
}) => {
  return (
    <div className="plss-download-prompt">
      <h3>🗺️ Map Data Required</h3>
      <p>
        To display this property on a map, we need to download Public Land Survey System (PLSS) 
        data for <strong>{state}</strong>.
      </p>
      <div className="download-info">
        <h4>One-time setup:</h4>
        <ul>
          <li>Downloads official PLSS data from the Bureau of Land Management</li>
          <li>Data is cached locally for future use</li>
          <li>Download size: ~10-50MB depending on state</li>
          <li>Only needs to be done once per state</li>
        </ul>
      </div>
      <button 
        className="download-button primary"
        onClick={onDownload}
      >
        📦 Download Map Data for {state}
      </button>
      <p className="disclaimer">
        Data source: Bureau of Land Management CadNSDI
      </p>
    </div>
  );
}; 