/**
 * Main Interactive Map Viewer Component
 * Displays interactive geographic map with polygon overlays
 */
import React, { useEffect, useRef, useState, useCallback } from 'react';
import { PolygonOverlay } from './PolygonOverlay';
import { MapControls } from './MapControls';
import { CoordinateDisplay } from './CoordinateDisplay';
import { TileLayerManager } from './TileLayerManager';
import { lonLatToPixel } from '../../utils/coordinateProjection';
import { mappingApi, type PLSSDescription } from '../../services/mappingApi';

interface MapViewerProps {
  polygonData?: any;
  initialCenter?: { lat: number; lon: number };
  initialZoom?: number;
  className?: string;
  plssAnchor?: PLSSDescription; // Optional: center tiles from PLSS section view
  plssPadding?: number; // Optional padding for section view bounds
}

interface MapState {
  center: { lat: number; lon: number };
  zoom: number;
  bounds: {
    min_lat: number;
    max_lat: number;
    min_lon: number;
    max_lon: number;
  };
  tileProvider: string;
  isLoading: boolean;
}

export const MapViewer: React.FC<MapViewerProps> = ({
  polygonData,
  initialCenter = { lat: 41.5, lon: -107.5 }, // Default Wyoming coordinates
  initialZoom = 10,
  className = "",
  plssAnchor,
  plssPadding = 0.2
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const [mapState, setMapState] = useState<MapState>({
    center: initialCenter,
    zoom: initialZoom,
    bounds: {
      min_lat: initialCenter.lat - 0.1,
      max_lat: initialCenter.lat + 0.1,
      min_lon: initialCenter.lon - 0.1,
      max_lon: initialCenter.lon + 0.1
    },
    tileProvider: 'usgs_topo',
    isLoading: false
  });

  const [mousePosition, setMousePosition] = useState<{ lat: number; lon: number } | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);

  // Calculate map dimensions and scaling
  const mapDimensions = React.useMemo(() => {
    if (!mapContainerRef.current) return null;

    const rect = mapContainerRef.current.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;

    // Calculate degrees per pixel based on current zoom and center
    const degreesPerPixelLat = (mapState.bounds.max_lat - mapState.bounds.min_lat) / height;
    const degreesPerPixelLon = (mapState.bounds.max_lon - mapState.bounds.min_lon) / width;

    return {
      width,
      height,
      degreesPerPixelLat,
      degreesPerPixelLon
    };
  }, [mapState.bounds, mapContainerRef.current]);

  // Convert screen coordinates to geographic coordinates
  const screenToGeo = useCallback((screenX: number, screenY: number) => {
    if (!mapDimensions) return null;

    const lat = mapState.bounds.max_lat - (screenY * mapDimensions.degreesPerPixelLat);
    const lon = mapState.bounds.min_lon + (screenX * mapDimensions.degreesPerPixelLon);

    return { lat, lon };
  }, [mapState.bounds, mapDimensions]);

  // Convert geographic coordinates to screen coordinates
  const geoToScreen = useCallback((lat: number, lon: number) => {
    if (!mapDimensions) return null;

    const x = (lon - mapState.bounds.min_lon) / mapDimensions.degreesPerPixelLon;
    const y = (mapState.bounds.max_lat - lat) / mapDimensions.degreesPerPixelLat;

    return { x, y };
  }, [mapState.bounds, mapDimensions]);

  // Shared Web Mercator pixel origin and toScreen that matches tile math
  const originPixel = React.useMemo(() => {
    return lonLatToPixel(mapState.bounds.min_lon, mapState.bounds.max_lat, Math.round(mapState.zoom));
  }, [mapState.bounds.min_lon, mapState.bounds.max_lat, mapState.zoom]);

  const toScreen = React.useCallback((lat: number, lon: number) => {
    const px = lonLatToPixel(lon, lat, Math.round(mapState.zoom));
    return { x: px.x - originPixel.x, y: px.y - originPixel.y };
  }, [mapState.zoom, originPixel]);

  // Handle mouse movement for coordinate display
  const handleMouseMove = useCallback((event: React.MouseEvent) => {
    if (!mapContainerRef.current) return;

    const rect = mapContainerRef.current.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    const geoCoords = screenToGeo(x, y);
    if (geoCoords) {
      setMousePosition(geoCoords);
    }

    // Handle dragging
    if (isDragging && dragStart) {
      const deltaX = x - dragStart.x;
      const deltaY = y - dragStart.y;

      if (mapDimensions) {
        const deltaLat = deltaY * mapDimensions.degreesPerPixelLat;
        const deltaLon = deltaX * mapDimensions.degreesPerPixelLon;

        setMapState(prev => ({
          ...prev,
          center: {
            lat: prev.center.lat + deltaLat,
            lon: prev.center.lon - deltaLon
          },
          bounds: {
            min_lat: prev.bounds.min_lat + deltaLat,
            max_lat: prev.bounds.max_lat + deltaLat,
            min_lon: prev.bounds.min_lon - deltaLon,
            max_lon: prev.bounds.max_lon - deltaLon
          }
        }));

        setDragStart({ x, y });
      }
    }
  }, [screenToGeo, isDragging, dragStart, mapDimensions]);

  // Handle mouse down for dragging
  const handleMouseDown = useCallback((event: React.MouseEvent) => {
    if (!mapContainerRef.current) return;

    const rect = mapContainerRef.current.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;

    setIsDragging(true);
    setDragStart({ x, y });
  }, []);

  // Handle mouse up
  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    setDragStart(null);
  }, []);

  // If PLSS anchor is provided, center map using section view (decouples tiles from georef output)
  useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (!plssAnchor) return;
      try {
        const res = await mappingApi.getPLSSSectionView(plssAnchor, plssPadding);
        if (!cancelled && res.success && res.bounds && res.center) {
          setMapState(prev => ({
            ...prev,
            center: res.center!,
            bounds: res.bounds
          }));
        }
      } catch (e) {
        // Ignore; keep previous state
      }
    };
    run();
    return () => { cancelled = true; };
  }, [plssAnchor, plssPadding]);

  // Handle zoom
  const handleZoom = useCallback((zoomDelta: number) => {
    setMapState(prev => {
      const newZoom = Math.max(1, Math.min(18, prev.zoom + zoomDelta));
      const zoomFactor = Math.pow(2, zoomDelta);
      
      const latRange = (prev.bounds.max_lat - prev.bounds.min_lat) / zoomFactor;
      const lonRange = (prev.bounds.max_lon - prev.bounds.min_lon) / zoomFactor;

      return {
        ...prev,
        zoom: newZoom,
        bounds: {
          min_lat: prev.center.lat - latRange / 2,
          max_lat: prev.center.lat + latRange / 2,
          min_lon: prev.center.lon - lonRange / 2,
          max_lon: prev.center.lon + lonRange / 2
        }
      };
    });
  }, []);

  // Handle wheel zoom
  const handleWheel = useCallback((event: React.WheelEvent) => {
    event.preventDefault();
    const zoomDelta = event.deltaY > 0 ? -0.5 : 0.5;
    handleZoom(zoomDelta);
  }, [handleZoom]);

  // Handle tile provider change
  const handleProviderChange = useCallback((provider: string) => {
    setMapState(prev => ({ ...prev, tileProvider: provider }));
  }, []);

  // Center map on polygon if provided AND no PLSS anchor (PLSS-driven tiles take precedence)
  useEffect(() => {
    if (!plssAnchor && polygonData && polygonData.bounds) {
      const bounds = polygonData.bounds;
      const centerLat = (bounds.min_lat + bounds.max_lat) / 2;
      const centerLon = (bounds.min_lon + bounds.max_lon) / 2;
      
      // Add padding to bounds
      const latPadding = (bounds.max_lat - bounds.min_lat) * 0.2;
      const lonPadding = (bounds.max_lon - bounds.min_lon) * 0.2;

      setMapState(prev => ({
        ...prev,
        center: { lat: centerLat, lon: centerLon },
        bounds: {
          min_lat: bounds.min_lat - latPadding,
          max_lat: bounds.max_lat + latPadding,
          min_lon: bounds.min_lon - lonPadding,
          max_lon: bounds.max_lon + lonPadding
        }
      }));
    }
  }, [polygonData, plssAnchor]);

  return (
    <div className={`map-viewer ${className}`}>
      {/* Map Container */}
      <div 
        ref={mapContainerRef}
        className="map-container"
        onMouseMove={handleMouseMove}
        onMouseDown={handleMouseDown}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        style={{
          width: '100%',
          height: '100%',
          position: 'relative',
          cursor: isDragging ? 'grabbing' : 'grab',
          overflow: 'hidden'
        }}
      >
        {/* Tile Layer */}
        <TileLayerManager
          bounds={mapState.bounds}
          zoom={mapState.zoom}
          provider={mapState.tileProvider}
          geoToScreen={geoToScreen}
          originPixel={originPixel}
        />

        {/* Polygon Overlay */}
        {polygonData && (
          <PolygonOverlay
            polygonData={polygonData}
            toScreen={toScreen}
            mapBounds={mapState.bounds}
          />
        )}

        {/* Loading Indicator */}
        {mapState.isLoading && (
          <div className="map-loading">
            <div className="loading-spinner">Loading map...</div>
          </div>
        )}
      </div>

      {/* Map Controls */}
      <MapControls
        zoom={mapState.zoom}
        onZoomIn={() => handleZoom(1)}
        onZoomOut={() => handleZoom(-1)}
        onProviderChange={handleProviderChange}
        currentProvider={mapState.tileProvider}
      />

      {/* Coordinate Display */}
      <CoordinateDisplay
        mousePosition={mousePosition}
        mapCenter={mapState.center}
        zoom={mapState.zoom}
      />
    </div>
  );
};