import React, { useEffect, useRef, useState } from 'react';
import { georeferenceApi, GeoreferenceProjectResponse, saveGeoreferenceForDossier } from '../../services/georeferenceApi';
import { MapWorkspace } from './MapWorkspace';

interface GeoreferenceControllerProps {
  schemaData?: any;
  polygonData?: any;
  className?: string;
  onPolygonUpdate?: (data: GeoreferenceProjectResponse) => void;
  dossierId?: string; // optional; if omitted, will attempt to derive from schemaData.metadata
}

/**
 * GeoreferenceController
 * - Orchestrates georeference operations using schema-based API
 * - Handles all georeference logic and state management
 * - Passes resulting polygon to MapWorkspace for display
 * - Maintains separation of concerns from map background components
 */
export const GeoreferenceController: React.FC<GeoreferenceControllerProps> = ({ 
  schemaData, 
  polygonData, 
  className = '',
  onPolygonUpdate,
  dossierId
}) => {
  const [georeferencedPolygonData, setGeoreferencedPolygonData] = useState<GeoreferenceProjectResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  // Prevent duplicate saves for the same computed result
  const lastSavedSignatureRef = useRef<string | null>(null);

  // Handle georeference when inputs change
  useEffect(() => {
    const performGeoreference = async () => {
      try {
        if (!polygonData || !schemaData) {
          setGeoreferencedPolygonData(null);
          setError(null);
          lastSavedSignatureRef.current = null;
          return;
        }

        setLoading(true);
        setError(null);
        lastSavedSignatureRef.current = null;

        console.log('🗺️ GeoreferenceController: Starting schema-based georeference');
        console.log('📊 Schema data:', schemaData);
        console.log('📊 Polygon data:', polygonData);

        // Use the new schema-based API endpoint
        const result = await georeferenceApi.projectFromSchema({
          schema_data: schemaData,
          polygon_data: polygonData
        });

        console.log('🔍 FULL RESPONSE DETAILS:');
        console.log('📊 Full result object:', JSON.stringify(result, null, 2));
        console.log('📊 result.anchor_info:', result.anchor_info);
        console.log('📊 result.anchor_info?.resolved_coordinates:', result.anchor_info?.resolved_coordinates);
        console.log('📊 result.geographic_polygon:', result.geographic_polygon);
        console.log('📊 result.geographic_polygon?.bounds:', result.geographic_polygon?.bounds);
        
        console.log('📊 Georeference API response:', {
          success: result.success,
          hasPolygon: !!result.geographic_polygon,
          bounds: result.geographic_polygon?.bounds,
          anchorInfo: result.anchor_info,
          error: result.error
        });

        if (result.success && result.geographic_polygon) {
          console.log('✅ GeoreferenceController: Polygon projection successful');
          console.log('📍 Polygon bounds:', result.geographic_polygon.bounds);
          console.log('📍 Anchor info:', result.anchor_info);
          
          setGeoreferencedPolygonData(result);
          onPolygonUpdate?.(result);

          // Attempt persistence (explicit save) if we know the dossier
          try {
            const derivedDossierId =
              dossierId ||
              schemaData?.metadata?.dossierId ||
              schemaData?.metadata?.dossier_id ||
              null;
            if (derivedDossierId) {
              const sig = JSON.stringify({
                coords: result.geographic_polygon.coordinates,
                bounds: result.geographic_polygon.bounds
              });
              if (sig !== lastSavedSignatureRef.current) {
                const meta: any = { source: 'auto-save-on-map' };
                if (schemaData?.schema_id) meta.schema_id = schemaData.schema_id;
                // Also attach schema_id directly into the georef_result for lineage
                const georefResultToSave: any = { ...result };
                if (schemaData?.schema_id && !georefResultToSave.schema_id) {
                  georefResultToSave.schema_id = schemaData.schema_id;
                }
                await saveGeoreferenceForDossier({
                  dossier_id: String(derivedDossierId),
                  georef_result: georefResultToSave,
                  metadata: meta
                });
                lastSavedSignatureRef.current = sig;
                console.log('💾 Georeference persisted for dossier', derivedDossierId);
              }
            } else {
              console.warn('⚠️ Skipping georef save: no dossierId available (pass prop or include schemaData.metadata.dossierId)');
            }
          } catch (saveErr) {
            console.warn('⚠️ Georeference save failed (non-blocking):', saveErr);
          }
        } else {
          console.error('❌ GeoreferenceController: Georeference failed:', result.error);
          setError(result.error || 'Projection failed');
        }

      } catch (error) {
        console.error('❌ GeoreferenceController: Projection error:', error);
        setError(error instanceof Error ? error.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    performGeoreference();
  }, [polygonData, schemaData, onPolygonUpdate]);

  // Calculate map center from georeferenced polygon data
  const mapCenter = React.useMemo(() => {
    console.log('🔍 MAP CENTER CALCULATION:');
    console.log('📊 georeferencedPolygonData:', georeferencedPolygonData);
    console.log('📊 anchor_info:', georeferencedPolygonData?.anchor_info);
    console.log('📊 resolved_coordinates:', georeferencedPolygonData?.anchor_info?.resolved_coordinates);
    
    if (georeferencedPolygonData?.anchor_info?.resolved_coordinates) {
      const coords = {
        lat: georeferencedPolygonData.anchor_info.resolved_coordinates.lat,
        lon: georeferencedPolygonData.anchor_info.resolved_coordinates.lon
      };
      console.log('🎯 GeoreferenceController: Using anchor coordinates for map center:', coords);
      return coords;
    }
    if (georeferencedPolygonData?.bounds) {
      const b = georeferencedPolygonData.bounds;
      const coords = {
        lat: (b.min_lat + b.max_lat) / 2,
        lon: (b.min_lon + b.max_lon) / 2
      };
      console.log('🎯 GeoreferenceController: Using bounds center for map center:', coords);
      return coords;
    }
    if (georeferencedPolygonData?.geographic_polygon?.bounds) {
      const b = georeferencedPolygonData.geographic_polygon.bounds;
      const coords = {
        lat: (b.min_lat + b.max_lat) / 2,
        lon: (b.min_lon + b.max_lon) / 2
      };
      console.log('🎯 GeoreferenceController: Using nested bounds center for map center:', coords);
      return coords;
    }
    console.log('🎯 GeoreferenceController: Using default Wyoming center');
    return { lat: 41.5, lon: -107.5 }; // Wyoming default
  }, [georeferencedPolygonData]);

  // Calculate zoom level from polygon bounds
  const mapZoom = React.useMemo(() => {
    if (georeferencedPolygonData?.bounds) {
      const b = georeferencedPolygonData.bounds;
      const latSpan = b.max_lat - b.min_lat;
      const lonSpan = b.max_lon - b.min_lon;
      const span = Math.max(latSpan, lonSpan);
      
      if (span > 0) {
        const zoom = Math.floor(14 - Math.log2(span));
        console.log('🎯 GeoreferenceController: Calculated zoom from bounds:', zoom);
        return Math.max(10, Math.min(18, zoom)); // Clamp between 10-18
      }
    }
    if (georeferencedPolygonData?.geographic_polygon?.bounds) {
      const b = georeferencedPolygonData.geographic_polygon.bounds;
      const latSpan = b.max_lat - b.min_lat;
      const lonSpan = b.max_lon - b.min_lon;
      const span = Math.max(latSpan, lonSpan);
      
      if (span > 0) {
        const zoom = Math.floor(14 - Math.log2(span));
        console.log('🎯 GeoreferenceController: Calculated zoom from nested bounds:', zoom);
        return Math.max(10, Math.min(18, zoom)); // Clamp between 10-18
      }
    }
    console.log('🎯 GeoreferenceController: Using default zoom level');
    return 12; // Default zoom
  }, [georeferencedPolygonData]);

  return (
    <div className={`georeference-controller ${className}`} style={{ width: '100%', height: '100%' }}>
      {loading && (
        <div className="absolute top-4 left-4 z-10 bg-blue-500 text-white px-3 py-1 rounded text-sm">
          Georeferencing...
        </div>
      )}
      
      {error && (
        <div className="absolute top-4 left-4 z-10 bg-red-500 text-white px-3 py-1 rounded text-sm">
          Error: {error}
        </div>
      )}

      {/* MapWorkspace handles the actual map display with georeferenced polygon */}
      <MapWorkspace 
        initialView={{ center: mapCenter, zoom: mapZoom }}
        initialParcels={georeferencedPolygonData ? [georeferencedPolygonData] : []}
        schemaData={schemaData}
      />
    </div>
  );
};

export default GeoreferenceController;


