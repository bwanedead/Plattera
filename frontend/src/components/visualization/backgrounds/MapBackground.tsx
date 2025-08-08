/**
 * Map Background Component
 * Renders live map tiles with PLSS integration
 */
import React, { useMemo, useRef, useState, useCallback, useEffect } from 'react';
import { usePLSSData } from '../../../hooks/usePLSSData';
import { PLSSDownloadModal } from '../../ui';
import { TileLayerManager } from '../../mapping/TileLayerManager';
import { lonLatToPixel, pixelToLonLat } from '../../../utils/coordinateProjection';
import { PolygonOverlay } from '../../mapping/PolygonOverlay';

interface MapBackgroundProps {
  schemaData: any;
  polygonData?: any | null; // georeferenced polygon for overlay (optional)
  showGrid?: boolean; // present in hybrid mode but unused here
}

export const MapBackground: React.FC<MapBackgroundProps> = ({ schemaData, polygonData }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const dragStartRef = useRef<{ x: number; y: number } | null>(null);
  const { status, state, error, modalDismissed, downloadData, dismissModal } = usePLSSData(schemaData);

  // Move ALL hooks to the top level - this fixes the "more hooks than previous render" error
  const mapBounds = useMemo(() => {
    // Default to Wyoming area if no specific bounds available
    return {
      min_lat: 41.0,
      max_lat: 45.0,
      min_lon: -111.0,
      max_lon: -104.0
    };
  }, []);

  // Determine view (bounds + zoom) based on projected polygon if available
  const initialView = useMemo(() => {
    // Determine center
    let centerLat = (mapBounds.min_lat + mapBounds.max_lat) / 2;
    let centerLon = (mapBounds.min_lon + mapBounds.max_lon) / 2;
    let zoom = 8;

    if (polygonData?.geographic_polygon?.bounds) {
      const b = polygonData.geographic_polygon.bounds;
      centerLat = (b.min_lat + b.max_lat) / 2;
      centerLon = (b.min_lon + b.max_lon) / 2;
      zoom = 16; // tighten to make polygon visible by default
    }
    // enforce integer zoom to align with tile grid
    zoom = Math.round(zoom);

    const viewportW = containerRef.current?.clientWidth || Math.min(window.innerWidth, 1200);
    const viewportH = containerRef.current?.clientHeight || Math.min(window.innerHeight, 800);

    // Compute top-left pixel so that center stays in the middle of viewport
    const centerPx = lonLatToPixel(centerLon, centerLat, zoom);
    const originPx = { x: centerPx.x - viewportW / 2, y: centerPx.y - viewportH / 2 };

    // Convert viewport corners back to lon/lat to get bounds
    const [minLon, maxLat] = pixelToLonLat(originPx.x, originPx.y, zoom);
    const [maxLon, minLat] = pixelToLonLat(originPx.x + viewportW, originPx.y + viewportH, zoom);

    return {
      bounds: {
        min_lat: minLat,
        max_lat: maxLat,
        min_lon: minLon,
        max_lon: maxLon,
      },
      zoom,
      originPx,
    };
  }, [polygonData, mapBounds, containerRef.current]);

  const [view, setView] = useState(initialView);

  // Re-initialize view when inputs change / container sized
  useEffect(() => {
    setView(initialView);
    // Debug: log initial map view
    console.log(
      `🧭 Map view init -> zoom: ${initialView.zoom}, bounds: ` +
      `(${initialView.bounds.min_lat.toFixed(5)}, ${initialView.bounds.min_lon.toFixed(5)}) .. ` +
      `(${initialView.bounds.max_lat.toFixed(5)}, ${initialView.bounds.max_lon.toFixed(5)})`,
      polygonData?.geographic_polygon?.bounds
        ? { polygonBounds: polygonData.geographic_polygon.bounds }
        : undefined
    );
  }, [initialView]);

  // Geographic to screen conversion consistent with current view
  const geoToScreen = useMemo(() => {
    const z = Math.round(view.zoom);
    const origin = lonLatToPixel(view.bounds.min_lon, view.bounds.max_lat, z);
    return (lat: number, lon: number) => {
      const p = lonLatToPixel(lon, lat, z);
      return { x: p.x - origin.x, y: p.y - origin.y };
    };
  }, [view]);

  // Helper to map screen pixel -> lon/lat for current view
  const screenToGeo = useCallback((x: number, y: number) => {
    const z = Math.round(view.zoom);
    const origin = lonLatToPixel(view.bounds.min_lon, view.bounds.max_lat, z);
    const [lon, lat] = pixelToLonLat(origin.x + x, origin.y + y, z);
    return { lat, lon };
  }, [view]);

  // Wheel zoom handler (zoom around pointer)
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const focusGeo = screenToGeo(px, py);

    // Integer zoom steps to align with tile grid; prevents overlay drift
    const delta = e.deltaY > 0 ? -1 : 1;
    const newZoom = Math.max(4, Math.min(18, Math.round(view.zoom + delta)));

    // Compute new origin so focusGeo stays under the pointer
    const focusPxNew = lonLatToPixel(focusGeo.lon, focusGeo.lat, newZoom);
    const originX = focusPxNew.x - px;
    const originY = focusPxNew.y - py;
    const rectW = rect.width, rectH = rect.height;
    const [minLon, maxLat] = pixelToLonLat(originX, originY, newZoom);
    const [maxLon, minLat] = pixelToLonLat(originX + rectW, originY + rectH, newZoom);

    setView({
      bounds: { min_lat: minLat, max_lat: maxLat, min_lon: minLon, max_lon: maxLon },
      zoom: newZoom,
      originPx: { x: originX, y: originY }
    });
    // Debug: log zoom change
    if (newZoom !== view.zoom) {
      console.log(
        `🔎 Zoom change ${view.zoom} -> ${newZoom}, bounds: ` +
        `(${minLat.toFixed(5)}, ${minLon.toFixed(5)}) .. (${maxLat.toFixed(5)}, ${maxLon.toFixed(5)})`
      );
    }
  }, [view, screenToGeo]);

  // Drag panning
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    dragStartRef.current = { x: e.clientX - rect.left, y: e.clientY - rect.top };
    setIsDragging(true);
  }, []);

  const handleMouseUp = useCallback(() => {
    setIsDragging(false);
    dragStartRef.current = null;
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging || !containerRef.current || !dragStartRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;
    const dx = x - dragStartRef.current.x;
    const dy = y - dragStartRef.current.y;

    // Translate bounds by pixel delta using integer zoom to match tiles
    const z = Math.round(view.zoom);
    const origin = lonLatToPixel(view.bounds.min_lon, view.bounds.max_lat, z);
    const originX = origin.x - dx;
    const originY = origin.y - dy;
    const [minLon, maxLat] = pixelToLonLat(originX, originY, z);
    const [maxLon, minLat] = pixelToLonLat(originX + rect.width, originY + rect.height, z);

    setView({ bounds: { min_lat: minLat, max_lat: maxLat, min_lon: minLon, max_lon: maxLon }, zoom: view.zoom, originPx: { x: originX, y: originY } });
    dragStartRef.current = { x, y };
  }, [isDragging, view]);

  const handleDownload = () => {
    downloadData();
  };

  const handleCancel = () => {
    dismissModal(); // Properly dismiss the modal
  };

  // Show modal when data is missing AND not dismissed
  const shouldShowModal = status === 'missing' && !modalDismissed;

  // Show loading during download
  if (status === 'downloading') {
    return (
      <>
        <div className="map-loading">
          <div className="spinner"></div>
          <p>Downloading {state} PLSS data...</p>
        </div>
        <PLSSDownloadModal
          isOpen={true}
          state={state || 'Unknown'}
          onDownload={handleDownload}
          onCancel={handleCancel}
          isDownloading={true}
        />
      </>
    );
  }

  // Show map when ready
  if (status === 'ready') {
    return (
      <div
        ref={containerRef}
        className="map-container"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{ position: 'relative', width: '100%', height: '100%', cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        <TileLayerManager
          bounds={view.bounds}
          zoom={view.zoom}
          provider="usgs_topo"
          geoToScreen={geoToScreen}
        />

        {/* Geographic polygon overlay (only if georeferenced) */}
        {polygonData && (
          <PolygonOverlay
            polygonData={polygonData}
            geoToScreen={geoToScreen}
            mapBounds={mapBounds}
          />
        )}
        
        {/* Status overlay */}
        {/* Status overlay removed for cleaner UX */}
        {/* <div style={{
          position: 'absolute',
          top: 10,
          left: 10,
          background: 'rgba(0,0,0,0.7)',
          color: 'white',
          padding: '8px 12px',
          borderRadius: '4px',
          fontSize: '12px',
          zIndex: 1000
        }}>
          🗺️ USGS Topo | {state} | Zoom: {view.zoom}
        </div> */}
      </div>
    );
  }

  // Error state or missing data that was dismissed
  if (status === 'error' || (status === 'missing' && modalDismissed)) {
    return (
      <div className="map-placeholder">
        {status === 'error' ? (
          <p>❌ Error: {error}</p>
        ) : (
          <p>🗺️ Map view requires PLSS data download. Click refresh to try again.</p>
        )}
      </div>
    );
  }

  // Default: show modal for missing data
  return (
    <>
      <div className="map-placeholder">
        <p>Preparing map view...</p>
      </div>
      <PLSSDownloadModal
        isOpen={shouldShowModal}
        state={state || 'Unknown'}
        onDownload={handleDownload}
        onCancel={handleCancel}
        isDownloading={false}
      />
    </>
  );
};