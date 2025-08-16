import React, { useEffect, useRef, useMemo } from 'react';
import maplibregl, { Map as MapLibreMap, LngLatBoundsLike } from 'maplibre-gl';
// CSS is imported globally in pages/_app.tsx
import { mappingApi, type PLSSDescription } from '../../services/mappingApi';

interface MapViewerProps {
  polygonData?: any;
  initialCenter?: { lat: number; lon: number };
  initialZoom?: number;
  className?: string;
  plssAnchor?: PLSSDescription;
  plssPadding?: number;
}

const API_BASE = 'http://localhost:8000/api/mapping';

export const MapViewer: React.FC<MapViewerProps> = ({
  polygonData,
  initialCenter = { lat: 41.5, lon: -107.5 },
  initialZoom = 10,
  className = '',
  plssAnchor,
  plssPadding = 0.2
}) => {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);

  // Determine the best center coordinates based on available data
  const bestCenter = useMemo(() => {
    // 1. If we have polygon data with georeferenced coordinates, use that
    if (polygonData?.anchor_info?.resolved_coordinates) {
      const coords = polygonData.anchor_info.resolved_coordinates;
      return { lat: coords.lat, lon: coords.lon };
    }
    
    // 2. If we have polygon bounds, use the center of those bounds
    if (polygonData?.bounds) {
      const b = polygonData.bounds;
    return {
        lat: (b.min_lat + b.max_lat) / 2,
        lon: (b.min_lon + b.max_lon) / 2
      };
    }
    
    // 3. Fall back to initial center
    return initialCenter;
  }, [polygonData, initialCenter]);

  // Determine the best zoom level based on available data
  const bestZoom = useMemo(() => {
    // If we have polygon bounds, calculate appropriate zoom
    if (polygonData?.bounds) {
      const b = polygonData.bounds;
      const latSpan = b.max_lat - b.min_lat;
      const lonSpan = b.max_lon - b.min_lon;
      const maxSpan = Math.max(latSpan, lonSpan);
      
      // Rough zoom calculation - adjust based on span
      if (maxSpan > 0.1) return 10;      // Large area
      if (maxSpan > 0.01) return 14;     // Medium area
      if (maxSpan > 0.001) return 16;    // Small area
      return 18;                         // Very small area
    }
    
    return initialZoom;
  }, [polygonData, initialZoom]);

  const setGeoJSONSource = (id: string, data: any) => {
    const map = mapRef.current;
    if (!map) return;
    if (map.getSource(id)) {
      (map.getSource(id) as any).setData(data);
    } else {
      map.addSource(id, { type: 'geojson', data });
    }
  };

  const ensureLineLayer = (id: string, source: string, color = '#444', width = 1, before?: string) => {
    const map = mapRef.current;
    if (!map) return;
    if (!map.getLayer(id)) {
      map.addLayer(
        { id, type: 'line', source, paint: { 'line-color': color, 'line-width': width } },
        before
      );
    }
  };

  const ensureFillLayer = (id: string, source: string, before?: string) => {
    const map = mapRef.current;
    if (!map) return;
    if (!map.getLayer(`${id}-fill`)) {
      map.addLayer(
        { id: `${id}-fill`, type: 'fill', source, paint: { 'fill-color': '#3b82f6', 'fill-opacity': 0.3 } },
        before
      );
    }
    if (!map.getLayer(`${id}-outline`)) {
      map.addLayer(
        { id: `${id}-outline`, type: 'line', source, paint: { 'line-color': '#3b82f6', 'line-width': 2 } },
        before
      );
    }
  };

  // Initialize map once with best available center and zoom
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    console.log(`🗺️ Initializing map at center: ${bestCenter.lat}, ${bestCenter.lon}, zoom: ${bestZoom}`);

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: { version: 8, sources: {}, layers: [] } as any,
      center: [bestCenter.lon, bestCenter.lat],
      zoom: bestZoom,
      attributionControl: true
    });

    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left');

    map.on('load', () => {
      // Add basemap tiles
      const provider = 'usgs_topo';
      const rasterId = 'basemap';
      if (!map.getSource(rasterId)) {
        map.addSource(rasterId, {
          type: 'raster',
          tiles: [`${API_BASE}/tile/${provider}/{z}/{x}/{y}`],
          tileSize: 256,
          attribution: '© USGS'
        });
      }
      if (!map.getLayer(rasterId)) {
        map.addLayer({ id: rasterId, type: 'raster', source: rasterId });
      }

      // If polygon already available, add its layer
      if (polygonData?.geographic_polygon) {
        setGeoJSONSource('parcel', polygonData.geographic_polygon);
        ensureFillLayer('parcel', 'parcel');
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [bestCenter.lat, bestCenter.lon, bestZoom]);

  // Load PLSS overlays when plssAnchor is provided
  useEffect(() => {
    const map = mapRef.current;
    let cancelled = false;
    if (!map || !plssAnchor) return;

    (async () => {
      try {
        console.log('🗺️ Loading PLSS section overlay for:', plssAnchor);
        
        const sec = await mappingApi.getPLSSSectionView(plssAnchor, plssPadding);
        if (!sec?.success || !sec.bounds) return;
        if (cancelled) return;
        
        const b = sec.bounds;
        const bounds: LngLatBoundsLike = [ [b.min_lon, b.min_lat], [b.max_lon, b.max_lat] ];
        map.fitBounds(bounds, { padding: 24, duration: 0 });

        const overlay = await mappingApi.getPLSSOverlay(plssAnchor);
        if (cancelled || !overlay?.success) return;
        
        if (overlay.section) {
          setGeoJSONSource('plss-section', overlay.section);
          ensureLineLayer('plss-section-outline', 'plss-section', '#666', 1.5, 'parcel-fill');
        }
        if (overlay.township) {
          setGeoJSONSource('plss-township', overlay.township);
          ensureLineLayer('plss-township-outline', 'plss-township', '#999', 1, 'plss-section-outline');
        }
        if (Array.isArray(overlay.splits) && overlay.splits.length > 0) {
          setGeoJSONSource('plss-splits', { type: 'FeatureCollection', features: overlay.splits });
          ensureLineLayer('plss-splits-lines', 'plss-splits', '#bbb', 0.75, 'plss-township-outline');
        }
      } catch (error) {
        console.warn('PLSS overlay load failed:', error);
      }
    })();

    return () => { cancelled = true; };
  }, [plssAnchor, plssPadding]);

  // Update polygon display when polygonData changes
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !polygonData?.geographic_polygon) return;
    
    console.log('🏠 Adding parcel polygon to map');
    setGeoJSONSource('parcel', polygonData.geographic_polygon);
    ensureFillLayer('parcel', 'parcel', 'plss-splits-lines');
    
    // If we have polygon bounds and no PLSS anchor, fit to polygon bounds
    if (!plssAnchor && polygonData?.bounds) {
      const b = polygonData.bounds;
      const bounds: LngLatBoundsLike = [ [b.min_lon, b.min_lat], [b.max_lon, b.max_lat] ];
      map.fitBounds(bounds, { padding: 24, duration: 0 });
    }
  }, [polygonData, plssAnchor]);

  return (
    <div 
      ref={containerRef} 
      className={`map-viewer ${className}`}
      style={{ width: '100%', height: '100%' }}
    />
  );
};