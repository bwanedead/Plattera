import React, { useState, useEffect } from 'react';
import { CleanMap } from '../../mapping/CleanMap';
import { cleanMappingApi } from '../../../services/cleanMappingApi';
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
  const [geoPolygonData, setGeoPolygonData] = useState<any>(null);
  const [isProjecting, setIsProjecting] = useState(false);
  const [projectionError, setProjectionError] = useState<string | null>(null);

  // Get PLSS state from schema data
  const state = schemaData?.descriptions?.[0]?.plss?.state;
  
  // Use PLSS data hook for download management
  const {
    status: plssStatus,
    progress,
    error: plssError,
    downloadData,
    cancelDownload,
    dismissModal
  } = usePLSSData(schemaData);

  // Project polygon when we have both polygon and PLSS data ready
  useEffect(() => {
    const projectPolygon = async () => {
      try {
        if (!polygonData || !schemaData || plssStatus !== 'ready') {
          setGeoPolygonData(null);
          return;
        }

        setIsProjecting(true);
        setProjectionError(null);

        console.log('🗺️ Starting polygon projection');

        // Extract PLSS from the first complete description
        const descriptions = Array.isArray(schemaData?.descriptions) ? schemaData.descriptions : [];
        const chosen = descriptions.find((d: any) => d?.is_complete && d?.plss) || descriptions[0];
        const plss = chosen?.plss;

        if (!plss) {
          setProjectionError('No PLSS data found in schema');
          return;
        }

        // Convert to projection request
        const request = cleanMappingApi.convertFromSchema(polygonData, plss);
        if (!request) {
          setProjectionError('Failed to convert polygon data');
          return;
        }

        // Project coordinates
        const result = await cleanMappingApi.projectPolygon(request);

        if (result.success && result.geographic_polygon) {
          console.log('✅ Polygon projection successful');
          setGeoPolygonData(result);
          onPolygonUpdate?.(result);
        } else {
          setProjectionError(result.error || 'Projection failed');
        }

      } catch (error) {
        console.error('❌ Projection error:', error);
        setProjectionError(error instanceof Error ? error.message : 'Unknown error');
      } finally {
        setIsProjecting(false);
      }
    };

    projectPolygon();
  }, [polygonData, schemaData, plssStatus, onPolygonUpdate]);

  // Calculate map center from polygon data
  const mapCenter = React.useMemo(() => {
    if (geoPolygonData?.anchor_info?.resolved_coordinates) {
      return {
        lat: geoPolygonData.anchor_info.resolved_coordinates.lat,
        lon: geoPolygonData.anchor_info.resolved_coordinates.lon
      };
    }
    if (geoPolygonData?.bounds) {
      const b = geoPolygonData.bounds;
      return {
        lat: (b.min_lat + b.max_lat) / 2,
        lon: (b.min_lon + b.max_lon) / 2
      };
    }
    return { lat: 41.5, lon: -107.5 }; // Wyoming default
  }, [geoPolygonData]);

  // Calculate zoom level from polygon bounds
  const mapZoom = React.useMemo(() => {
    if (geoPolygonData?.bounds) {
      const b = geoPolygonData.bounds;
      const latSpan = b.max_lat - b.min_lat;
      const lonSpan = b.max_lon - b.min_lon;
      const maxSpan = Math.max(latSpan, lonSpan);
      
      if (maxSpan > 0.1) return 10;
      if (maxSpan > 0.01) return 14;
      if (maxSpan > 0.001) return 16;
      return 18;
    }
    return 10;
  }, [geoPolygonData]);

  // Show download modal when PLSS data is missing
  if (plssStatus === 'missing') {
    return (
      <div className="clean-map-background">
        <div className="map-placeholder">
          <div className="placeholder-content">
            <h3>🗺️ Map Data Required</h3>
            <p>PLSS data for {state || 'this area'} is required to display the map.</p>
            <button onClick={downloadData} className="download-button">
              📦 Download Map Data
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show download progress
  if (plssStatus === 'downloading') {
    return (
      <div className="clean-map-background">
        <div className="map-placeholder">
          <div className="placeholder-content">
            <div className="loading-spinner"></div>
            <h3>Downloading Map Data</h3>
            <p>{progress || 'Preparing download...'}</p>
            <button onClick={cancelDownload} className="cancel-button">
              Cancel
            </button>
          </div>
        </div>
        <PLSSDownloadModal
          isOpen={true}
          state={state || 'Unknown'}
          onDownload={downloadData}
          onCancel={cancelDownload}
          isDownloading={true}
          progressText={progress}
          onHardCancel={cancelDownload}
        />
      </div>
    );
  }

  // Show projection loading
  if (isProjecting) {
    return (
      <div className="clean-map-background">
        <div className="map-placeholder">
          <div className="placeholder-content">
            <div className="loading-spinner"></div>
            <h3>Projecting Coordinates</h3>
            <p>Converting local coordinates to geographic...</p>
          </div>
        </div>
      </div>
    );
  }

  // Show projection error
  if (projectionError) {
    return (
      <div className="clean-map-background">
        <div className="map-placeholder">
          <div className="placeholder-content">
            <h3>❌ Projection Error</h3>
            <p>{projectionError}</p>
            <button onClick={() => window.location.reload()} className="retry-button">
              Retry
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show PLSS error
  if (plssError) {
    return (
      <div className="clean-map-background">
        <div className="map-placeholder">
          <div className="placeholder-content">
            <h3>❌ PLSS Data Error</h3>
            <p>{plssError}</p>
            <button onClick={downloadData} className="retry-button">
              Retry Download
            </button>
          </div>
        </div>
      </div>
    );
  }

  // Show the map
  return (
    <div className="clean-map-background">
      <CleanMap
        center={mapCenter}
        zoom={mapZoom}
        polygonData={geoPolygonData}
        className="full-size"
        onMapLoad={() => console.log('🗺️ Clean map loaded')}
      />
    </div>
  );
};
