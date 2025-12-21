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
    uiProgress,
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

  const isError = plssStatus === 'error';
  const shouldShowPromptModal =
    (plssStatus === 'missing' || plssStatus === 'canceled') && !modalDismissed;

  // Show explicit error prompt with retry when a download fails.
  if (isError && !modalDismissed) {
    return (
      <PLSSDownloadModal
        isOpen={true}
        state={state || 'Unknown'}
        onDownload={downloadData}
        onCancel={handleCancel}
        isDownloading={false}
        progressText={null}
        onHardCancel={undefined}
        parquetPhase={false}
        estimatedTime={null}
        parquetStatus={null}
        progressPercent={null}
        progressBar="none"
        progressHeadline={`PLSS download failed for ${state || 'this state'}.`}
        progressDetail={plssError || 'An unknown error occurred while downloading PLSS data. You can retry.'}
        progressRawStage={null}
      />
    );
  }

  // Show PLSS download prompt when data is missing / canceled. Active download
  // progress is owned by the global overlay + banner, not this map component.
  if (shouldShowPromptModal) {
    return (
      <PLSSDownloadModal
        isOpen={true}
        state={state || 'Unknown'}
        onDownload={downloadData}
        onCancel={handleCancel}
        isDownloading={false}
        progressText={null}
        onHardCancel={undefined}
        parquetPhase={false}
        estimatedTime={null}
        parquetStatus={null}
        progressPercent={null}
        progressBar="none"
        progressHeadline={null}
        progressDetail={null}
        progressRawStage={null}
      />
    );
  }

  // During active download, show a lightweight loading placeholder; the
  // detailed progress UI is handled globally by the overlay + banner.
  if (plssStatus === 'downloading') {
    return (
      <div className="flex items-center justify-center h-full bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-600">Downloading PLSS data for {state}...</p>
        </div>
      </div>
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
