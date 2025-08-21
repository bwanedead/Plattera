/**
 * Container Overlay Manager
 * Dedicated manager for container-based PLSS overlays
 * Handles loading, unloading, and visibility of container overlays
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ContainerApi, ContainerLayer, ContainerRequest } from '../../../services/plss/containerApi';

export interface ContainerOverlayState {
  showTownship: boolean;
  showRange: boolean;
  showGrid: boolean;
  showSections: boolean;
  showQuarterSections: boolean;
}

interface ContainerOverlayManagerProps {
  map: any;
  schemaData?: any;
  containerBounds?: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
  state?: string;
  overlayState: ContainerOverlayState;
  onOverlayLoad?: (layer: ContainerLayer, features: any[]) => void;
  onOverlayError?: (layer: ContainerLayer, error: string) => void;
  onOverlayUnload?: (layer: ContainerLayer) => void;
}

export const ContainerOverlayManager: React.FC<ContainerOverlayManagerProps> = ({
  map,
  schemaData,
  containerBounds,
  state,
  overlayState,
  onOverlayLoad,
  onOverlayError,
  onOverlayUnload,
}) => {
  const [activeLayers, setActiveLayers] = useState<Set<ContainerLayer>>(new Set());
  const [loadingLayers, setLoadingLayers] = useState<Set<ContainerLayer>>(new Set());
  const [layerData, setLayerData] = useState<Map<ContainerLayer, any[]>>(new Map());
  const [layerErrors, setLayerErrors] = useState<Map<ContainerLayer, string>>(new Map());
  
  const containerApi = useRef(new ContainerApi());
  const abortController = useRef<AbortController | null>(null);

  // Get layer color for map styling
  const getLayerColor = useCallback((layer: ContainerLayer): string => {
    switch (layer) {
      case 'township': return '#ff0000'; // Red
      case 'range': return '#00ff00';     // Green
      case 'grid': return '#0000ff';      // Blue
      case 'sections': return '#ffff00';  // Yellow
      case 'quarter-sections': return '#ff00ff'; // Magenta
      default: return '#cccccc';
    }
  }, []);

  // Get layer opacity for map styling
  const getLayerOpacity = useCallback((layer: ContainerLayer): number => {
    switch (layer) {
      case 'township': return 0.8;
      case 'range': return 0.8;
      case 'grid': return 0.6;
      case 'sections': return 0.4;
      case 'quarter-sections': return 0.3;
      default: return 0.5;
    }
  }, []);

  // Load a single container overlay layer
  const loadLayer = useCallback(async (layer: ContainerLayer) => {
    if (!schemaData || !containerBounds || !state) {
      console.warn('❌ Missing required data for container overlay:', { schemaData: !!schemaData, containerBounds: !!containerBounds, state: !!state });
      return;
    }

    // Cancel any existing request
    if (abortController.current) {
      abortController.current.abort();
    }
    abortController.current = new AbortController();

    setLoadingLayers(prev => new Set(prev).add(layer));
    setLayerErrors(prev => {
      const newMap = new Map(prev);
      newMap.delete(layer);
      return newMap;
    });

    try {
      const request: ContainerRequest = {
        schema_data: schemaData,
        container_bounds: containerBounds,
      };

      // Validate request before sending
      const validation = containerApi.current.validateRequest(request);
      if (!validation.valid) {
        throw new Error(`Invalid request: ${validation.errors.join(', ')}`);
      }

      const result = await containerApi.current.getOverlay(
        layer, 
        state, 
        request, 
        abortController.current.signal
      );

      // Add to map
      const layerId = `container-${layer}`;
      
      // Remove existing layer if it exists
      if (map.getLayer(layerId)) {
        map.removeLayer(layerId);
      }
      if (map.getSource(layerId)) {
        map.removeSource(layerId);
      }

      // Add new source and layer
      map.addSource(layerId, {
        type: 'geojson',
        data: result,
      });

      map.addLayer({
        id: layerId,
        type: 'line',
        source: layerId,
        paint: {
          'line-color': getLayerColor(layer),
          'line-width': 2,
          'line-opacity': getLayerOpacity(layer),
        },
        layout: {
          'line-join': 'round',
          'line-cap': 'round',
        },
      });

      // Update state
      setLayerData(prev => new Map(prev).set(layer, result.features));
      setActiveLayers(prev => new Set(prev).add(layer));
      
      onOverlayLoad?.(layer, result.features);

      console.log(`✅ Container ${layer} overlay loaded: ${result.features.length} features`);

    } catch (error: unknown) {
      if (error instanceof Error && error.name === 'AbortError') {
        console.log(`🔄 Container ${layer} overlay request cancelled`);
        return;
      }
      
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      console.error(`❌ Container ${layer} overlay failed:`, error);
      setLayerErrors(prev => new Map(prev).set(layer, errorMessage));
      onOverlayError?.(layer, errorMessage);
    } finally {
      setLoadingLayers(prev => {
        const newSet = new Set(prev);
        newSet.delete(layer);
        return newSet;
      });
    }
  }, [map, schemaData, containerBounds, state, onOverlayLoad, onOverlayError, getLayerColor, getLayerOpacity]);

  // Unload a single container overlay layer
  const unloadLayer = useCallback((layerType: string) => {
    if (!map || !map.getCanvas()) {
      console.log(`⚠️ Map not available when trying to unload ${layerType}`);
      return;
    }
    
    try {
      const layerId = `container-${layerType}`;
      const sourceId = `container-${layerType}-source`;
      
      // Check if layer exists before trying to remove it
      if (map.getLayer && map.getLayer(layerId)) {
        map.removeLayer(layerId);
      }
      
      // Check if source exists before trying to remove it
      if (map.getSource && map.getSource(sourceId)) {
        map.removeSource(sourceId);
      }
      
      console.log(`🗑️ Container ${layerType} overlay unloaded`);
    } catch (error) {
      console.warn(`⚠️ Error unloading ${layerType}:`, error);
    }
  }, [map]);

  // Determine which layers should be active based on overlay state
  const getDesiredLayers = useCallback((): ContainerLayer[] => {
    const layers: ContainerLayer[] = [];
    
    if (overlayState.showGrid || (overlayState.showTownship && overlayState.showRange)) {
      layers.push('grid');
    } else {
      if (overlayState.showTownship) layers.push('township');
      if (overlayState.showRange) layers.push('range');
    }
    
    if (overlayState.showSections) layers.push('sections');
    if (overlayState.showQuarterSections) layers.push('quarter-sections');
    
    return layers;
  }, [overlayState]);

  // Update overlays based on state changes
  useEffect(() => {
    const desiredLayers = getDesiredLayers();
    const currentLayers = Array.from(activeLayers);
    
    // Unload layers that are no longer desired
    currentLayers.forEach(layer => {
      if (!desiredLayers.includes(layer)) {
        unloadLayer(layer);
        setActiveLayers(prev => {
          const newSet = new Set(prev);
          newSet.delete(layer);
          return newSet;
        });
      }
    });
    
    // Load layers that are desired but not active
    desiredLayers.forEach(layer => {
      if (!activeLayers.has(layer) && !loadingLayers.has(layer)) {
        loadLayer(layer);
      }
    });
  }, [overlayState, getDesiredLayers, loadLayer, unloadLayer]); // Simplified dependencies

  // Cleanup on unmount only
  useEffect(() => {
    return () => {
      if (abortController.current) {
        abortController.current.abort();
      }
      // Clean up all layers on unmount
      ['township', 'range', 'grid', 'sections', 'quarter-sections'].forEach(layer => {
        try {
          const layerId = `container-${layer}`;
          const sourceId = `container-${layer}-source`;
          
          if (map?.getLayer?.(layerId)) {
            map.removeLayer(layerId);
          }
          if (map?.getSource?.(sourceId)) {
            map.removeSource(sourceId);
          }
        } catch (error) {
          // Ignore cleanup errors
        }
      });
    };
  }, [map]); // Only depend on map, not activeLayers

  // Don't render anything - this is a logic-only component
  return null;
};

export default ContainerOverlayManager;
