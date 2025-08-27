import React, { useState, useEffect } from 'react';
import { MapWorkspace } from '../../mapping/MapWorkspace';
import { georeferenceApi, GeoreferenceProjectRequest } from '../../../services/georeferenceApi';
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
    dismissModal,
    parquetPhase,
    estimatedTime,
    parquetStatus
  } = usePLSSData(schemaData);

  // Convert schema data to georeference request
  const convertToGeoreferenceRequest = (polygonData: any, plss: any): GeoreferenceProjectRequest | null => {
    try {
      if (!polygonData?.coordinates || !plss) {
        console.log('❌ Missing polygon coordinates or PLSS data');
        return null;
      }

      console.log('🔄 Converting to georeference request:', {
        polygonCoords: polygonData.coordinates,
        plss: plss
      });

      // Convert coordinates to required format
      const local_coordinates = polygonData.coordinates.map((coord: any) => {
        if (Array.isArray(coord)) {
          return { x: coord[0], y: coord[1] };
        } else if (coord && typeof coord === 'object' && 'x' in coord && 'y' in coord) {
          return { x: coord.x, y: coord.y };
        }
        throw new Error('Invalid coordinate format');
      });

      // Extract PLSS anchor from schema
      const plss_anchor = {
        state: plss.state,
        township_number: plss.township_number,
        township_direction: plss.township_direction,
        range_number: plss.range_number,
        range_direction: plss.range_direction,
        section_number: plss.section_number,
        quarter_sections: plss.quarter_sections,
        principal_meridian: plss.principal_meridian
      };

      const request: GeoreferenceProjectRequest = {
        local_coordinates,
        plss_anchor
      };

      // Add starting point if available
      if (polygonData?.origin?.reference_corner || polygonData?.origin?.bearing || polygonData?.origin?.distance_feet) {
        request.starting_point = {
          tie_to_corner: {
            corner_label: polygonData?.origin?.reference_corner,
            bearing_raw: polygonData?.origin?.bearing,
            distance_value: polygonData?.origin?.distance_feet,
            distance_units: 'feet',
            tie_direction: 'corner_bears_from_pob'
          }
        };
        console.log('📍 Added tie-to-corner:', request.starting_point.tie_to_corner);
      }

      console.log('✅ Georeference request prepared:', request);
      return request;
    } catch (error) {
      console.error('❌ Schema conversion failed:', error);
      return null;
    }
  };

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

        console.log('🗺️ Starting polygon projection with new georeference API');

        // Extract PLSS from the first complete description
        const descriptions = Array.isArray(schemaData?.descriptions) ? schemaData.descriptions : [];
        const chosen = descriptions.find((d: any) => d?.is_complete && d?.plss) || descriptions[0];
        const plss = chosen?.plss;

        if (!plss) {
          setProjectionError('No PLSS data found in schema');
          return;
        }

        console.log('📋 Extracted PLSS data:', plss);

        // Convert to georeference request
        const request = convertToGeoreferenceRequest(polygonData, plss);
        if (!request) {
          setProjectionError('Failed to convert polygon data');
          return;
        }

        // Project coordinates using new georeference API
        console.log('🚀 Calling georeference API...');
        const result = await georeferenceApi.project(request);

        console.log('📊 Georeference API response:', {
          success: result.success,
          hasPolygon: !!result.geographic_polygon,
          bounds: result.geographic_polygon?.bounds,
          anchorInfo: result.anchor_info,
          error: result.error
        });

        if (result.success && result.geographic_polygon) {
          console.log('✅ Polygon projection successful');
          console.log('📍 Polygon bounds:', result.geographic_polygon.bounds);
          console.log('📍 Anchor info:', result.anchor_info);
          setGeoPolygonData(result);
          onPolygonUpdate?.(result);
        } else {
          console.error('❌ Georeference failed:', result.error);
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
      const coords = {
        lat: geoPolygonData.anchor_info.resolved_coordinates.lat,
        lon: geoPolygonData.anchor_info.resolved_coordinates.lon
      };
      console.log('🎯 CleanMapBackground: Using anchor coordinates for map center:', coords);
      return coords;
    }
    if (geoPolygonData?.bounds) {
      const b = geoPolygonData.bounds;
      const coords = {
        lat: (b.min_lat + b.max_lat) / 2,
        lon: (b.min_lon + b.max_lon) / 2
      };
      console.log('🎯 CleanMapBackground: Using bounds center for map center:', coords);
      return coords;
    }
    if (geoPolygonData?.geographic_polygon?.bounds) {
      const b = geoPolygonData.geographic_polygon.bounds;
      const coords = {
        lat: (b.min_lat + b.max_lat) / 2,
        lon: (b.min_lon + b.max_lon) / 2
      };
      console.log('🎯 CleanMapBackground: Using nested bounds center for map center:', coords);
      return coords;
    }
    console.log('🎯 CleanMapBackground: Using default Wyoming center');
    return { lat: 41.5, lon: -107.5 }; // Wyoming default
  }, [geoPolygonData]);

  // Calculate zoom level from polygon bounds
  const mapZoom = React.useMemo(() => {
    const b = geoPolygonData?.bounds || geoPolygonData?.geographic_polygon?.bounds;
    if (b) {
      const latSpan = b.max_lat - b.min_lat;
      const lonSpan = b.max_lon - b.min_lon;
      const maxSpan = Math.max(latSpan, lonSpan);
      
      let zoom = 10;
      if (maxSpan > 0.1) zoom = 6;        // Was 10, now 6 (4 levels lower)
      else if (maxSpan > 0.01) zoom = 10; // Was 14, now 10 (4 levels lower) 
      else if (maxSpan > 0.001) zoom = 12; // Was 16, now 12 (4 levels lower)
      else zoom = 14;                     // Was 18, now 14 (4 levels lower)
      
      console.log('🎯 CleanMapBackground: Calculated zoom level:', zoom, 'for span:', maxSpan);
      return zoom;
    }
    console.log('🎯 CleanMapBackground: Using default zoom level: 10');
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
          parquetPhase={!!parquetPhase}
          parquetStatus={parquetStatus || undefined}
          estimatedTime={estimatedTime || undefined}
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
      <MapWorkspace
        standalone={false}
        initialParcels={geoPolygonData ? [geoPolygonData] : []}
        schemaData={schemaData}
        initialView={{
          center: mapCenter,
          zoom: mapZoom
        }}
        className="full-size"
      />
    </div>
  );
};
