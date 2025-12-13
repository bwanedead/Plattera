import React from 'react';
import { GeoreferenceController } from '../../mapping/GeoreferenceController';
import { usePLSSData } from '../../../hooks/usePLSSData';
import { PLSSDownloadModal } from '../../ui';
// Styles moved to global import in pages/_app.tsx to satisfy Next.js CSS rules

interface CleanMapBackgroundProps {
  schemaData?: any;
  polygonData?: any;
  onPolygonUpdate?: (data: any) => void;
  dossierId?: string; // optional pass-through
  extraParcels?: any[]; // optional extra saved plots to display concurrently
  onCancel?: () => void; // optional cancel handler so parent can leave map view
}

export const CleanMapBackground: React.FC<CleanMapBackgroundProps> = ({
  schemaData,
  polygonData,
  onPolygonUpdate,
  dossierId,
  extraParcels,
  onCancel,
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
    parquetStatus,
    modalDismissed,
  } = usePLSSData(schemaData);

  // Handle Cancel: mark modal dismissed and let parent leave map/hybrid view
  const handleCancel = () => {
    try {
      dismissModal();
    } catch (e) {
      console.error('Error dismissing PLSS modal', e);
    }
    try {
      onCancel?.();
    } catch (e) {
      console.error('Error in CleanMapBackground onCancel', e);
    }
  };

  const isDownloading = plssStatus === 'downloading';
  const shouldShowModal =
    isDownloading ||
    plssStatus === 'error' ||
    (plssStatus === 'missing' && !modalDismissed);

  // Show PLSS download modal if needed, respecting dismissal for "missing" state
  if (shouldShowModal) {
    return (
      <PLSSDownloadModal
        isOpen={true}
        state={state || 'Unknown'}
        onDownload={isDownloading ? undefined : downloadData}
        onCancel={handleCancel}
        isDownloading={isDownloading}
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
        dossierId={dossierId || schemaData?.metadata?.dossierId || schemaData?.metadata?.dossier_id}
        extraParcels={extraParcels}
        className="w-full h-full"
      />
    </div>
  );
};
