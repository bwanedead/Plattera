import React, { useEffect } from 'react';
import maplibregl from 'maplibre-gl';
import { useMapContext } from '../core/MapContext';

interface ParcelOverlayProps {
  parcels: any[];
}

export const ParcelOverlay: React.FC<ParcelOverlayProps> = ({ parcels }) => {
  const { map, isLoaded } = useMapContext();

  useEffect(() => {
    if (!map || !isLoaded || !parcels || parcels.length === 0) return;

    const parcel = parcels[0]; // Use first parcel
    if (!parcel?.geographic_polygon) return;

    console.log('🏠 ParcelOverlay: Adding parcel polygon to map:', {
      hasPolygon: !!parcel.geographic_polygon,
      coordinates: parcel.geographic_polygon.coordinates,
      bounds: parcel.geographic_polygon.bounds,
      anchorInfo: parcel.anchor_info
    });

    // Debug: Log first few polygon coordinates
    if (parcel.geographic_polygon.coordinates?.[0]) {
      console.log('🏠 Polygon first 3 coordinates:', parcel.geographic_polygon.coordinates[0].slice(0, 3));
    }

    // Extra diagnostics: list POB and resolved corner if present
    if (parcel?.anchor_info) {
      const ai = parcel.anchor_info;
      console.log('📍 Anchor diagnostics:', {
        pob_coordinates: ai.pob_coordinates,
        resolved_corner: ai.resolved_coordinates,
        pob_method: ai.pob_method
      });
    }

    try {
      // Remove existing parcel layers
      if (map.getLayer('parcel-fill')) map.removeLayer('parcel-fill');
      if (map.getLayer('parcel-outline')) map.removeLayer('parcel-outline');
      if (map.getSource('parcel')) map.removeSource('parcel');

      // Add parcel source
      map.addSource('parcel', {
        type: 'geojson',
        data: parcel.geographic_polygon
      });

      // Add fill layer
      map.addLayer({
        id: 'parcel-fill',
        type: 'fill',
        source: 'parcel',
        paint: {
          'fill-color': '#3b82f6',
          'fill-opacity': 0.3
        }
      });

      // Add outline layer
      map.addLayer({
        id: 'parcel-outline',
        type: 'line',
        source: 'parcel',
        paint: {
          'line-color': '#3b82f6',
          'line-width': 2,
          'line-opacity': 0.8
        }
      });

      // Fit to parcel bounds if available
      const b = parcel.geographic_polygon?.bounds || parcel.bounds;
      if (b) {
        console.log('🎯 ParcelOverlay: Fitting map to parcel bounds:', b);
        const bounds = new maplibregl.LngLatBounds(
          [b.min_lon, b.min_lat],
          [b.max_lon, b.max_lat]
        );
        
        map.fitBounds(bounds, { 
          padding: 50,
          duration: 1000
        });
      }

    } catch (error) {
      console.error('❌ ParcelOverlay: Failed to add parcel to map:', error);
    }

    return () => {
      // Cleanup on unmount
      try {
        if (map.getLayer('parcel-fill')) map.removeLayer('parcel-fill');
        if (map.getLayer('parcel-outline')) map.removeLayer('parcel-outline');
        if (map.getSource('parcel')) map.removeSource('parcel');
      } catch (error) {
        console.warn('ParcelOverlay cleanup error:', error);
      }
    };
  }, [map, isLoaded, parcels]);

  return null; // This is an overlay component, it doesn't render UI
};
