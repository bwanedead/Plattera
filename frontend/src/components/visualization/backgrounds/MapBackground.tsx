/**
 * Map Background - Pure presentation component
 * Uses hook for state management, delegates UI to specialized components
 */
import React from 'react';
import { usePLSSData } from '../../../hooks/usePLSSData';
import { PLSSDownloadPrompt } from '../../mapping/PLSSDownloadPrompt';
import { MapStatusDisplay } from '../../mapping/MapStatusDisplay';

interface MapBackgroundProps {
  schemaData?: any; // Changed from polygon to schemaData
  showGrid?: boolean;
}

export const MapBackground: React.FC<MapBackgroundProps> = ({
  schemaData, // Changed from polygon to schemaData
  showGrid
}) => {
  const { status, state, error, progress, downloadData } = usePLSSData(schemaData);

  const renderContent = () => {
    if (status === 'missing' && state) {
      return (
        <PLSSDownloadPrompt 
          state={state} 
          onDownload={downloadData} 
        />
      );
    }

    return (
      <MapStatusDisplay
        status={status}
        state={state}
        error={error}
        progress={progress}
        onRetry={downloadData}
      />
    );
  };

  return (
    <div className="map-background">
      <div className="map-container">
        {renderContent()}
      </div>
    </div>
  );
};