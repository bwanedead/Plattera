import React, { useEffect, useRef } from 'react';
import maplibregl, { Map as MapLibreMap, LngLatBoundsLike } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
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

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: { version: 8, sources: {}, layers: [] } as any,
      center: [initialCenter.lon, initialCenter.lat],
      zoom: initialZoom,
      attributionControl: true
    });
    mapRef.current = map;
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.addControl(new maplibregl.ScaleControl({ unit: 'imperial' }), 'bottom-left');

    map.on('load', () => {
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
      if (polygonData?.geographic_polygon) {
        setGeoJSONSource('parcel', polygonData.geographic_polygon);
        ensureFillLayer('parcel', 'parcel');
      }
    });

    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, [initialCenter.lat, initialCenter.lon, initialZoom]);

  useEffect(() => {
    const map = mapRef.current;
    let cancelled = false;
    if (!map || !plssAnchor) return;

    (async () => {
      try {
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
      } catch {
        // ignore
      }
    })();

    return () => { cancelled = true; };
  }, [plssAnchor, plssPadding]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !polygonData?.geographic_polygon) return;
    setGeoJSONSource('parcel', polygonData.geographic_polygon);
    ensureFillLayer('parcel', 'parcel', 'plss-splits-lines');
    if (!plssAnchor && polygonData?.bounds) {
      const b = polygonData.bounds;
      const bounds: LngLatBoundsLike = [ [b.min_lon, b.min_lat], [b.max_lon, b.max_lat] ];
      map.fitBounds(bounds, { padding: 24, duration: 0 });
    }
  }, [polygonData, plssAnchor]);

  return (
    <div className={`map-viewer ${className}`} style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div ref={containerRef} style={{ position: 'absolute', inset: 0 }} />
    </div>
  );
};