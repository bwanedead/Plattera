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
        <h4>One-time setup (offline):</h4>
        <ul>
          <li>Downloads official Wyoming PLSS as File Geodatabases (Townships, Sections, Subdivisions)</li>
          <li>No live server limits; faster and more reliable mapping</li>
          <li>Approximate size: ~700MB compressed; ~0.8–1.6GB installed</li>
        </ul>
      </div>
      <button 
        className="download-button primary"
        onClick={onDownload}
      >
        📦 Download Map Data for {state}
      </button>
      <p className="disclaimer">Data source: BLM ArcGIS Hub (CadNSDI)</p>
    </div>
  );
}; 