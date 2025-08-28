import React from 'react';
import { GeoreferenceController } from '../../mapping/GeoreferenceController';
import { usePLSSData } from '../../../hooks/usePLSSData';
import { PLSSDownloadModal } from '../../ui';
// Styles moved to global import in pages/_app.tsx to satisfy Next.js CSS rules

interface CleanMapBackgroundProps {
  schemaData?: any;
  polygonData?: any;
  onPolygonUpdate?: (data: any) => void;
}

export const CleanMapBackground: React.FC<CleanMapBackgroundProps> = ({
  schemaData,
  polygonData,
  onPolygonUpdate
}) => {
  // Get PLSS state from schema data
  const state = schemaData?.descriptions?.[0]?.plss?.state;
  
  // Use PLSS data hook for download management
  const {
    status: plssStatus,
    progress,
    error: plssError,
    downloadData,
    cancelDownload,
    dismissModal,
    parquetPhase,
    estimatedTime,
    parquetStatus
  } = usePLSSData(schemaData);

  // Show PLSS download modal if needed
  if (plssStatus === 'downloading' || plssStatus === 'error') {
    return (
      <PLSSDownloadModal
        isOpen={true}
        state={state || 'Unknown'}
        onDownload={downloadData}
        onCancel={cancelDownload}
        isDownloading={plssStatus === 'downloading'}
        progressText={progress}
        onHardCancel={cancelDownload}
        parquetPhase={parquetPhase}
        estimatedTime={estimatedTime}
        parquetStatus={parquetStatus}
      />
    );
  }

  // Show loading state while PLSS data is being checked
  if (plssStatus === 'checking') {
    return (
      <div className="flex items-center justify-center h-full bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-600">Checking PLSS data for {state}...</p>
        </div>
      </div>
    );
  }

  // When PLSS is ready, render the GeoreferenceController
  return (
    <div className="clean-map-background w-full h-full">
      <GeoreferenceController
        schemaData={schemaData}
        polygonData={polygonData}
        onPolygonUpdate={onPolygonUpdate}
        className="w-full h-full"
      />
    </div>
  );
};
