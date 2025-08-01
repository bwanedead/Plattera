/**
 * Map State Hook
 * Manages map interaction state and viewport
 */
import { useState, useCallback, useRef } from 'react';

export interface MapBounds {
  min_lat: number;
  max_lat: number;
  min_lon: number;
  max_lon: number;
}

export interface MapViewport {
  center: { lat: number; lon: number };
  zoom: number;
  bounds: MapBounds;
}

export interface MapInteractionState {
  isDragging: boolean;
  dragStart: { x: number; y: number } | null;
  isLoading: boolean;
  mousePosition: { lat: number; lon: number } | null;
}

export interface UseMapStateOptions {
  initialCenter?: { lat: number; lon: number };
  initialZoom?: number;
  minZoom?: number;
  maxZoom?: number;
}

export interface UseMapStateReturn {
  // Viewport state
  viewport: MapViewport;
  interaction: MapInteractionState;
  
  // Viewport controls
  setCenter: (center: { lat: number; lon: number }) => void;
  setZoom: (zoom: number) => void;
  setBounds: (bounds: MapBounds) => void;
  
  // Interaction handlers
  handleMouseMove: (screenX: number, screenY: number, mapDimensions: any) => void;
  handleMouseDown: (screenX: number, screenY: number) => void;
  handleMouseUp: () => void;
  handleWheel: (deltaY: number) => void;
  
  // Coordinate conversion utilities
  screenToGeo: (screenX: number, screenY: number, mapDimensions: any) => { lat: number; lon: number } | null;
  geoToScreen: (lat: number, lon: number, mapDimensions: any) => { x: number; y: number } | null;
  
  // Utility functions
  fitToBounds: (bounds: MapBounds, padding?: number) => void;
  zoomIn: () => void;
  zoomOut: () => void;
  resetView: () => void;
}

export const useMapState = (options: UseMapStateOptions = {}): UseMapStateReturn => {
  const {
    initialCenter = { lat: 41.5, lon: -107.5 },
    initialZoom = 10,
    minZoom = 1,
    maxZoom = 18
  } = options;

  // Calculate initial bounds
  const calculateBounds = useCallback((center: { lat: number; lon: number }, zoom: number): MapBounds => {
    // Approximate degrees per zoom level
    const latRange = 180 / Math.pow(2, zoom - 1);
    const lonRange = 360 / Math.pow(2, zoom - 1);
    
    return {
      min_lat: center.lat - latRange / 2,
      max_lat: center.lat + latRange / 2,
      min_lon: center.lon - lonRange / 2,
      max_lon: center.lon + lonRange / 2
    };
  }, []);

  // Viewport state
  const [viewport, setViewport] = useState<MapViewport>({
    center: initialCenter,
    zoom: initialZoom,
    bounds: calculateBounds(initialCenter, initialZoom)
  });

  // Interaction state
  const [interaction, setInteraction] = useState<MapInteractionState>({
    isDragging: false,
    dragStart: null,
    isLoading: false,
    mousePosition: null
  });

  // Store initial state for reset
  const initialStateRef = useRef({
    center: initialCenter,
    zoom: initialZoom,
    bounds: calculateBounds(initialCenter, initialZoom)
  });

  // Coordinate conversion functions
  const screenToGeo = useCallback((screenX: number, screenY: number, mapDimensions: any) => {
    if (!mapDimensions) return null;

    const lat = viewport.bounds.max_lat - (screenY * mapDimensions.degreesPerPixelLat);
    const lon = viewport.bounds.min_lon + (screenX * mapDimensions.degreesPerPixelLon);

    return { lat, lon };
  }, [viewport.bounds]);

  const geoToScreen = useCallback((lat: number, lon: number, mapDimensions: any) => {
    if (!mapDimensions) return null;

    const x = (lon - viewport.bounds.min_lon) / mapDimensions.degreesPerPixelLon;
    const y = (viewport.bounds.max_lat - lat) / mapDimensions.degreesPerPixelLat;

    return { x, y };
  }, [viewport.bounds]);

  // Viewport control functions
  const setCenter = useCallback((center: { lat: number; lon: number }) => {
    setViewport(prev => ({
      ...prev,
      center,
      bounds: calculateBounds(center, prev.zoom)
    }));
  }, [calculateBounds]);

  const setZoom = useCallback((zoom: number) => {
    const clampedZoom = Math.max(minZoom, Math.min(maxZoom, zoom));
    setViewport(prev => ({
      ...prev,
      zoom: clampedZoom,
      bounds: calculateBounds(prev.center, clampedZoom)
    }));
  }, [calculateBounds, minZoom, maxZoom]);

  const setBounds = useCallback((bounds: MapBounds) => {
    const centerLat = (bounds.min_lat + bounds.max_lat) / 2;
    const centerLon = (bounds.min_lon + bounds.max_lon) / 2;
    
    setViewport(prev => ({
      ...prev,
      center: { lat: centerLat, lon: centerLon },
      bounds
    }));
  }, []);

  // Interaction handlers
  const handleMouseMove = useCallback((screenX: number, screenY: number, mapDimensions: any) => {
    // Update mouse position
    const geoCoords = screenToGeo(screenX, screenY, mapDimensions);
    setInteraction(prev => ({
      ...prev,
      mousePosition: geoCoords
    }));

    // Handle dragging
    if (interaction.isDragging && interaction.dragStart && mapDimensions) {
      const deltaX = screenX - interaction.dragStart.x;
      const deltaY = screenY - interaction.dragStart.y;

      const deltaLat = deltaY * mapDimensions.degreesPerPixelLat;
      const deltaLon = deltaX * mapDimensions.degreesPerPixelLon;

      setViewport(prev => ({
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

      setInteraction(prev => ({
        ...prev,
        dragStart: { x: screenX, y: screenY }
      }));
    }
  }, [screenToGeo, interaction.isDragging, interaction.dragStart]);

  const handleMouseDown = useCallback((screenX: number, screenY: number) => {
    setInteraction(prev => ({
      ...prev,
      isDragging: true,
      dragStart: { x: screenX, y: screenY }
    }));
  }, []);

  const handleMouseUp = useCallback(() => {
    setInteraction(prev => ({
      ...prev,
      isDragging: false,
      dragStart: null
    }));
  }, []);

  const handleWheel = useCallback((deltaY: number) => {
    const zoomDelta = deltaY > 0 ? -0.5 : 0.5;
    setZoom(viewport.zoom + zoomDelta);
  }, [viewport.zoom, setZoom]);

  // Utility functions
  const fitToBounds = useCallback((bounds: MapBounds, padding: number = 0.1) => {
    // Add padding
    const latPadding = (bounds.max_lat - bounds.min_lat) * padding;
    const lonPadding = (bounds.max_lon - bounds.min_lon) * padding;

    const paddedBounds: MapBounds = {
      min_lat: bounds.min_lat - latPadding,
      max_lat: bounds.max_lat + latPadding,
      min_lon: bounds.min_lon - lonPadding,
      max_lon: bounds.max_lon + lonPadding
    };

    setBounds(paddedBounds);
  }, [setBounds]);

  const zoomIn = useCallback(() => {
    setZoom(viewport.zoom + 1);
  }, [viewport.zoom, setZoom]);

  const zoomOut = useCallback(() => {
    setZoom(viewport.zoom - 1);
  }, [viewport.zoom, setZoom]);

  const resetView = useCallback(() => {
    setViewport(initialStateRef.current);
    setInteraction({
      isDragging: false,
      dragStart: null,
      isLoading: false,
      mousePosition: null
    });
  }, []);

  return {
    viewport,
    interaction,
    setCenter,
    setZoom,
    setBounds,
    handleMouseMove,
    handleMouseDown,
    handleMouseUp,
    handleWheel,
    screenToGeo,
    geoToScreen,
    fitToBounds,
    zoomIn,
    zoomOut,
    resetView
  };
};