/**
 * Map Status Display - Pure UI for different states
 * Handles only presentation logic
 */
import React from 'react';
import { PLSSDataStatus } from '../../services/plssDataService';

interface MapStatusDisplayProps {
  status: PLSSDataStatus;
  state: string | null;
  error: string | null;
  progress: string | null;
  onRetry?: () => void;
}

export const MapStatusDisplay: React.FC<MapStatusDisplayProps> = ({
  status,
  state,
  error,
  progress,
  onRetry
}) => {
  switch (status) {
    case 'checking':
      return (
        <div className="map-status loading">
          <div className="loading-spinner">⏳</div>
          <h3>Loading Map...</h3>
          <p>Checking data availability</p>
        </div>
      );

    case 'downloading':
      return (
        <div className="map-status downloading">
          <div className="loading-spinner">📦</div>
          <h3>Downloading Map Data...</h3>
          <p>{progress}</p>
          <div className="progress-note">
            Please wait, this may take a few minutes...
          </div>
        </div>
      );

    case 'ready':
      return (
        <div className="map-status ready">
          <h3>🗺️ Map Ready</h3>
          <p>PLSS data loaded for {state}</p>
          <p className="coming-soon">
            Full map visualization coming soon!<br/>
            Will show polygon overlay on USGS topographic base map.
          </p>
        </div>
      );

    case 'error':
      return (
        <div className="map-status error">
          <div className="error-icon">❌</div>
          <h3>Map Error</h3>
          <p>{error}</p>
          {onRetry && (
            <button className="retry-button" onClick={onRetry}>
              🔄 Retry Download
            </button>
          )}
        </div>
      );

    default:
      return null;
  }
}; 