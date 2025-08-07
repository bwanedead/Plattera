/**
 * Map Background Component
 * Renders live map tiles with PLSS integration
 */
import React, { useMemo } from 'react';
import { usePLSSData } from '../../../hooks/usePLSSData';
import { PLSSDownloadModal } from '../../ui';
import { TileLayerManager } from '../../mapping/TileLayerManager';
import { lonLatToPixel, TILE_SIZE } from '../../../utils/coordinateProjection';

interface MapBackgroundProps {
  schemaData: any;
}

export const MapBackground: React.FC<MapBackgroundProps> = ({ schemaData }) => {
  const { status, state, error, modalDismissed, downloadData, dismissModal } = usePLSSData(schemaData);

  // Move ALL hooks to the top level - this fixes the "more hooks than previous render" error
  const mapBounds = useMemo(() => {
    // Default to Wyoming area if no specific bounds available
    return {
      min_lat: 41.0,
      max_lat: 45.0,
      min_lon: -111.0,
      max_lon: -104.0
    };
  }, []);

  // Simple geographic to screen coordinate conversion
  const geoToScreen = useMemo(() => {
    return (lat: number, lon: number) => {
      const origin = lonLatToPixel(mapBounds.min_lon, mapBounds.max_lat, 8);
      const p = lonLatToPixel(lon, lat, 8);
      return { x: p.x - origin.x, y: p.y - origin.y };
    };
  }, [mapBounds]);

  const handleDownload = () => {
    downloadData();
  };

  const handleCancel = () => {
    dismissModal(); // Properly dismiss the modal
  };

  // Show modal when data is missing AND not dismissed
  const shouldShowModal = status === 'missing' && !modalDismissed;

  // Show loading during download
  if (status === 'downloading') {
    return (
      <>
        <div className="map-loading">
          <div className="spinner"></div>
          <p>Downloading {state} PLSS data...</p>
        </div>
        <PLSSDownloadModal
          isOpen={true}
          state={state || 'Unknown'}
          onDownload={handleDownload}
          onCancel={handleCancel}
          isDownloading={true}
        />
      </>
    );
  }

  // Show map when ready
  if (status === 'ready') {
    return (
      <div className="map-container" style={{ position: 'relative', width: '100%', height: '100%' }}>
        <TileLayerManager
          bounds={mapBounds}
          zoom={8} // Start with zoom level 8 for state-wide view
          provider="usgs_topo"
          geoToScreen={geoToScreen}
        />
        
        {/* Status overlay */}
        <div style={{
          position: 'absolute',
          top: 10,
          left: 10,
          background: 'rgba(0,0,0,0.7)',
          color: 'white',
          padding: '8px 12px',
          borderRadius: '4px',
          fontSize: '12px',
          zIndex: 1000
        }}>
          🗺️ USGS Topo | {state} | Zoom: 8
        </div>
      </div>
    );
  }

  // Error state or missing data that was dismissed
  if (status === 'error' || (status === 'missing' && modalDismissed)) {
    return (
      <div className="map-placeholder">
        {status === 'error' ? (
          <p>❌ Error: {error}</p>
        ) : (
          <p>🗺️ Map view requires PLSS data download. Click refresh to try again.</p>
        )}
      </div>
    );
  }

  // Default: show modal for missing data
  return (
    <>
      <div className="map-placeholder">
        <p>Preparing map view...</p>
      </div>
      <PLSSDownloadModal
        isOpen={shouldShowModal}
        state={state || 'Unknown'}
        onDownload={handleDownload}
        onCancel={handleCancel}
        isDownloading={false}
      />
    </>
  );
};