/**
 * Coordinate Display Component
 * Shows current mouse coordinates and map information
 */
import React from 'react';

interface CoordinateDisplayProps {
  mousePosition: { lat: number; lon: number } | null;
  mapCenter: { lat: number; lon: number };
  zoom: number;
}

export const CoordinateDisplay: React.FC<CoordinateDisplayProps> = ({
  mousePosition,
  mapCenter,
  zoom
}) => {
  // Format coordinate to specified decimal places
  const formatCoord = (value: number, decimals: number = 6): string => {
    return value.toFixed(decimals);
  };

  // Convert decimal degrees to degrees, minutes, seconds
  const toDMS = (decimal: number, isLongitude: boolean = false): string => {
    const degrees = Math.floor(Math.abs(decimal));
    const minutes = Math.floor((Math.abs(decimal) - degrees) * 60);
    const seconds = ((Math.abs(decimal) - degrees) * 60 - minutes) * 60;
    
    const direction = decimal >= 0 
      ? (isLongitude ? 'E' : 'N') 
      : (isLongitude ? 'W' : 'S');
    
    return `${degrees}° ${minutes}' ${seconds.toFixed(2)}" ${direction}`;
  };

  return (
    <div className="coordinate-display">
      {/* Mouse Position */}
      <div className="coordinate-section">
        <div className="coordinate-label">Cursor Position:</div>
        {mousePosition ? (
          <div className="coordinate-values">
            <div className="coordinate-row">
              <span className="coord-type">Lat:</span>
              <span className="coord-value">{formatCoord(mousePosition.lat)}</span>
              <span className="coord-dms">{toDMS(mousePosition.lat)}</span>
            </div>
            <div className="coordinate-row">
              <span className="coord-type">Lon:</span>
              <span className="coord-value">{formatCoord(mousePosition.lon)}</span>
              <span className="coord-dms">{toDMS(mousePosition.lon, true)}</span>
            </div>
          </div>
        ) : (
          <div className="coordinate-values">
            <div className="no-coordinates">Move mouse over map</div>
          </div>
        )}
      </div>

      {/* Map Center */}
      <div className="coordinate-section">
        <div className="coordinate-label">Map Center:</div>
        <div className="coordinate-values">
          <div className="coordinate-row">
            <span className="coord-type">Lat:</span>
            <span className="coord-value">{formatCoord(mapCenter.lat)}</span>
          </div>
          <div className="coordinate-row">
            <span className="coord-type">Lon:</span>
            <span className="coord-value">{formatCoord(mapCenter.lon)}</span>
          </div>
        </div>
      </div>

      {/* Map Info */}
      <div className="coordinate-section">
        <div className="coordinate-label">Map Info:</div>
        <div className="coordinate-values">
          <div className="coordinate-row">
            <span className="coord-type">Zoom:</span>
            <span className="coord-value">{zoom}</span>
          </div>
          <div className="coordinate-row">
            <span className="coord-type">Scale:</span>
            <span className="coord-value">1:{Math.round(591657527.591555 / Math.pow(2, zoom))}</span>
          </div>
        </div>
      </div>

      {/* Copy Coordinates Button */}
      {mousePosition && (
        <div className="coordinate-actions">
          <button
            className="copy-coords-button"
            onClick={() => {
              const coordText = `${formatCoord(mousePosition.lat)}, ${formatCoord(mousePosition.lon)}`;
              navigator.clipboard?.writeText(coordText);
              // Could add a toast notification here
            }}
            title="Copy coordinates to clipboard"
          >
            📋 Copy
          </button>
        </div>
      )}
    </div>
  );
};