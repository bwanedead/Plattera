import React, { useEffect, useRef, useState } from 'react';
import maplibregl from 'maplibre-gl';

interface CleanMapProps {
  center?: { lat: number; lon: number };
  zoom?: number;
  polygonData?: any;
  className?: string;
  onMapLoad?: () => void;
}

export const CleanMap: React.FC<CleanMapProps> = ({
  center = { lat: 41.5, lon: -107.5 },
  zoom = 10,
  polygonData,
  className = '',
  onMapLoad
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);

  // Initialize map once
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    console.log(`🗺️ Initializing clean map at ${center.lat}, ${center.lon}, zoom: ${zoom}`);

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: {
        version: 8,
        sources: {
          'raster-tiles': {
            type: 'raster',
            tiles: ['http://localhost:8000/api/mapping/tile/usgs_topo/{z}/{x}/{y}'],
            tileSize: 256,
            minzoom: 0,
            maxzoom: 16,
            attribution: '© USGS'
          }
        },
        layers: [
          {
            id: 'background',
            type: 'raster',
            source: 'raster-tiles'
          }
        ]
      },
      center: [center.lon, center.lat],
      zoom: zoom,
      maxZoom: 20,
      attributionControl: false
    });

    mapRef.current = map;

    // Add controls
    map.addControl(new maplibregl.NavigationControl(), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left');
    map.addControl(new maplibregl.AttributionControl(), 'bottom-right');

    // Handle load event
    map.on('load', () => {
      console.log('🗺️ Map loaded successfully');
      setIsLoaded(true);
      onMapLoad?.();
    });

    // Handle errors
    map.on('error', (e) => {
      console.error('🗺️ Map error:', e);
    });

    return () => {
      console.log('🗺️ Cleaning up map');
      map.remove();
      mapRef.current = null;
      setIsLoaded(false);
    };
  }, [center.lat, center.lon, zoom]);

  // Handle polygon data
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !isLoaded || !polygonData?.geographic_polygon) return;

    console.log('🏠 Adding polygon to map');

    try {
      // Remove existing polygon layers
      if (map.getLayer('polygon-fill')) map.removeLayer('polygon-fill');
      if (map.getLayer('polygon-outline')) map.removeLayer('polygon-outline');
      if (map.getSource('polygon')) map.removeSource('polygon');

      // Add polygon source
      map.addSource('polygon', {
        type: 'geojson',
        data: polygonData.geographic_polygon
      });

      // Add fill layer
      map.addLayer({
        id: 'polygon-fill',
        type: 'fill',
        source: 'polygon',
        paint: {
          'fill-color': '#3b82f6',
          'fill-opacity': 0.3
        }
      });

      // Add outline layer
      map.addLayer({
        id: 'polygon-outline',
        type: 'line',
        source: 'polygon',
        paint: {
          'line-color': '#3b82f6',
          'line-width': 2
        }
      });

      // Fit to polygon bounds if available
      if (polygonData.bounds) {
        const bounds = new maplibregl.LngLatBounds(
          [polygonData.bounds.min_lon, polygonData.bounds.min_lat],
          [polygonData.bounds.max_lon, polygonData.bounds.max_lat]
        );
        
        map.fitBounds(bounds, { 
          padding: 50,
          duration: 1000
        });
        
        console.log('🎯 Fitted map to polygon bounds');
      }

    } catch (error) {
      console.error('❌ Failed to add polygon to map:', error);
    }
  }, [polygonData, isLoaded]);

  return (
    <div className={`clean-map ${className}`}>
      <div 
        ref={containerRef} 
        style={{ width: '100%', height: '100%' }}
      />
      {!isLoaded && (
        <div className="map-loading-overlay">
          <div className="loading-spinner"></div>
          <p>Loading map...</p>
        </div>
      )}
    </div>
  );
};
