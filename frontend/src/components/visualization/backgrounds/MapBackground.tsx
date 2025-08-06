/**
 * Map Background Component
 * Uses modal for PLSS download instead of embedded message
 */
import React from 'react';
import { usePLSSData } from '../../../hooks/usePLSSData';
import { PLSSDownloadModal } from '../../mapping/PLSSDownloadModal';

interface MapBackgroundProps {
  schemaData: any;
}

export const MapBackground: React.FC<MapBackgroundProps> = ({ schemaData }) => {
  const { status, state, error, modalDismissed, downloadData, dismissModal } = usePLSSData(schemaData);

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
      <div className="map-ready">
        <p>🗺️ Map Ready</p>
        <p>PLSS data loaded for {state}</p>
        <p>Full map visualization coming soon!</p>
        <p>Will show polygon overlay on USGS topographic base map.</p>
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