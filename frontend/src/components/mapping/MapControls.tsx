/**
 * Map Controls Component
 * Provides zoom, pan, and layer controls for the map
 */
import React, { useState } from 'react';

interface MapControlsProps {
  zoom: number;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onProviderChange: (provider: string) => void;
  currentProvider: string;
}

const TILE_PROVIDERS = [
  { id: 'usgs_topo', name: 'USGS Topo', description: 'Topographic maps' },
  { id: 'usgs_imagery', name: 'USGS Imagery', description: 'Aerial imagery' },
  { id: 'osm_standard', name: 'OpenStreetMap', description: 'Street map' },
  { id: 'esri_world_topo', name: 'Esri Topo', description: 'World topographic' },
  { id: 'esri_world_imagery', name: 'Esri Imagery', description: 'World imagery' }
];

export const MapControls: React.FC<MapControlsProps> = ({
  zoom,
  onZoomIn,
  onZoomOut,
  onProviderChange,
  currentProvider
}) => {
  const [showLayerPanel, setShowLayerPanel] = useState(false);

  return (
    <div className="map-controls">
      {/* Zoom Controls */}
      <div className="zoom-controls">
        <button
          className="zoom-button zoom-in"
          onClick={onZoomIn}
          disabled={zoom >= 18}
          title="Zoom In"
        >
          +
        </button>
        
        <div className="zoom-level">
          {zoom}
        </div>
        
        <button
          className="zoom-button zoom-out"
          onClick={onZoomOut}
          disabled={zoom <= 1}
          title="Zoom Out"
        >
          −
        </button>
      </div>

      {/* Layer Controls */}
      <div className="layer-controls">
        <button
          className={`layer-toggle ${showLayerPanel ? 'active' : ''}`}
          onClick={() => setShowLayerPanel(!showLayerPanel)}
          title="Change Map Layer"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </button>

        {showLayerPanel && (
          <div className="layer-panel">
            <div className="layer-panel-header">
              <h4>Map Layers</h4>
              <button
                className="close-panel"
                onClick={() => setShowLayerPanel(false)}
              >
                ✕
              </button>
            </div>
            
            <div className="layer-list">
              {TILE_PROVIDERS.map(provider => (
                <div
                  key={provider.id}
                  className={`layer-option ${currentProvider === provider.id ? 'active' : ''}`}
                  onClick={() => {
                    onProviderChange(provider.id);
                    setShowLayerPanel(false);
                  }}
                >
                  <div className="layer-name">{provider.name}</div>
                  <div className="layer-description">{provider.description}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Additional Controls */}
      <div className="additional-controls">
        {/* Full Screen Toggle */}
        <button
          className="control-button fullscreen"
          onClick={() => {
            const mapElement = document.querySelector('.map-viewer') as HTMLElement;
            if (mapElement) {
              if (!document.fullscreenElement) {
                mapElement.requestFullscreen?.();
              } else {
                document.exitFullscreen?.();
              }
            }
          }}
          title="Toggle Fullscreen"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z"/>
          </svg>
        </button>

        {/* Reset View */}
        <button
          className="control-button reset-view"
          onClick={() => {
            // This would reset to initial view or polygon bounds
            console.log('Reset view');
          }}
          title="Reset View"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z"/>
          </svg>
        </button>
      </div>
    </div>
  );
};