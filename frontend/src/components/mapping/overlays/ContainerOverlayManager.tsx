/**
 * Container Overlay Manager
 * Dedicated manager for container-based PLSS overlays
 * Handles loading, unloading, and visibility of container overlays
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ContainerApi, ContainerLayer, ContainerRequest } from '../../../services/plss/containerApi';
import { ContainerOverlayState } from '../../../hooks/useContainerOverlayState';
import { ContainerLabelManager, ContainerLabelOptions } from './ContainerLabelManager';

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

  // Get layer color for map styling - clean, professional colors
  const getLayerColor = useCallback((layer: ContainerLayer): string => {
    switch (layer) {
      case 'township': return '#D2691E';    // Chocolate
      case 'range': return '#1E90FF';       // Dodger blue
      case 'grid': return '#DC143C';        // Crimson
      case 'sections': return '#228B22';    // Forest green
      case 'quarter-sections': return '#FF8C00'; // Dark orange
      case 'subdivisions': return '#9370DB'; // Medium purple
      default: return '#FF0000';
    }
  }, []);

  // Get layer opacity for map styling - adjusted for better visibility
  const getLayerOpacity = useCallback((layer: ContainerLayer): number => {
    switch (layer) {
      case 'township': return 0.9;        // Higher opacity for main boundaries
      case 'range': return 0.9;           // Higher opacity for main boundaries
      case 'grid': return 0.8;            // Strong visibility for grid
      case 'sections': return 0.6;        // Medium visibility for sections
      case 'quarter-sections': return 0.4; // Lower for fine detail
      case 'subdivisions': return 0.3;    // Lower for very fine detail
      default: return 0.5;
    }
  }, []);



  // 🎯 HELPER FUNCTIONS - Defined first to avoid scope issues
  
  const calculateBoundaryAngle = useCallback((coordinates: number[][], index: number): number => {
    const prevIndex = Math.max(0, index - 1);
    const nextIndex = Math.min(coordinates.length - 1, index + 1);
    
    const dx = coordinates[nextIndex][0] - coordinates[prevIndex][0];
    const dy = coordinates[nextIndex][1] - coordinates[prevIndex][1];
    
    return Math.atan2(dy, dx) * 180 / Math.PI;
  }, []);
  

  


  // Remove layer from map
  const removeLayerFromMap = useCallback((layer: ContainerLayer) => {
    if (!map) return;

    const layerId = `container-${layer}`;
    const sourceId = `container-${layer}-source`;

    try {
      // Remove layer overlays
      if (map.getLayer(layerId)) {
        map.removeLayer(layerId);
      }
      if (map.getSource(sourceId)) {
        map.removeSource(sourceId);
      }
      
      console.log(`🗑️ Container ${layer} overlay unloaded`);
    } catch (error) {
      console.warn(`⚠️ Error unloading ${layer}:`, error);
    }
  }, [map]);

  // Add layer to map with proper styling
  const addLayerToMap = useCallback((layer: ContainerLayer, features: any[]) => {
    if (!map) return;

    const layerId = `container-${layer}`;
    const sourceId = `container-${layer}-source`;
    const color = getLayerColor(layer);
    const opacity = getLayerOpacity(layer);

    // Remove existing layer if it exists
    if (map.getLayer(layerId)) {
      map.removeLayer(layerId);
    }
    if (map.getSource(sourceId)) {
      map.removeSource(sourceId);
    }

    // Add source
    map.addSource(sourceId, {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: features
      }
    });

    // Add layer with professional styling
    map.addLayer({
      id: layerId,
      type: 'line',
      source: sourceId,
      paint: {
        'line-color': color,
        'line-width': layer === 'grid' ? 3 : layer === 'township' || layer === 'range' ? 2 : 1,
        'line-opacity': opacity
      }
    });

    console.log(`✅ Added ${layer} layer to map with ${features.length} features`);
  }, [map, getLayerColor, getLayerOpacity]);

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

    try {
      console.log(`🚀 Loading container ${layer} overlay for ${state}`);
      
      const request: ContainerRequest = {
        schema_data: schemaData,
        container_bounds: containerBounds
      };

      const result = await containerApi.current.getOverlay(layer, state, request, abortController.current.signal);
      const features = result.features;
      
      console.log(`✅ Container ${layer} overlay loaded: ${features.length} features`);
      
      // Store the data
      setLayerData(prev => new Map(prev).set(layer, features));
      setActiveLayers(prev => new Set(prev).add(layer));
      setLayerErrors(prev => {
        const newErrors = new Map(prev);
        newErrors.delete(layer);
        return newErrors;
      });
      
      // Add to map
      addLayerToMap(layer, features);
      
      // Callback
      onOverlayLoad?.(layer, features);
      
    } catch (error: any) {
      console.error(`❌ Container ${layer} overlay failed:`, error);
      
      const errorMessage = error.message || 'Unknown error';
      setLayerErrors(prev => new Map(prev).set(layer, errorMessage));
      
      // Callback
      onOverlayError?.(layer, errorMessage);
    } finally {
      setLoadingLayers(prev => {
        const newLoading = new Set(prev);
        newLoading.delete(layer);
        return newLoading;
      });
    }
  }, [schemaData, containerBounds, state, onOverlayLoad, onOverlayError, addLayerToMap]);

  // Unload a single container overlay layer
  const unloadLayer = useCallback((layer: ContainerLayer) => {
    console.log(`🗑️ Unloading container ${layer} overlay`);
    
    // Remove from map
    removeLayerFromMap(layer);
    
    // Remove from state
    setActiveLayers(prev => {
      const newActive = new Set(prev);
      newActive.delete(layer);
      return newActive;
    });
    
    setLayerData(prev => {
      const newData = new Map(prev);
      newData.delete(layer);
      return newData;
    });
    
    setLayerErrors(prev => {
      const newErrors = new Map(prev);
      newErrors.delete(layer);
      return newErrors;
    });
    
    // Callback
    onOverlayUnload?.(layer);
  }, [removeLayerFromMap, onOverlayUnload]);



  // Handle overlay state changes
  useEffect(() => {
    if (!map) return;

    // Determine which layers should be active based on overlay state
    const desiredLayers = new Set<ContainerLayer>();
    
    if (overlayState.showGrid) desiredLayers.add('grid');
    if (overlayState.showTownship) desiredLayers.add('township');
    if (overlayState.showRange) desiredLayers.add('range');
    if (overlayState.showSections) desiredLayers.add('sections');
    if (overlayState.showQuarterSections) desiredLayers.add('quarter-sections');
    if (overlayState.showSubdivisions) desiredLayers.add('subdivisions');

    // Load new layers
    desiredLayers.forEach(layer => {
      if (!activeLayers.has(layer) && !loadingLayers.has(layer)) {
        loadLayer(layer);
      }
    });

    // Unload layers that are no longer needed
    activeLayers.forEach(layer => {
      if (!desiredLayers.has(layer)) {
        unloadLayer(layer);
      }
    });
  }, [map, overlayState, activeLayers, loadingLayers, loadLayer, unloadLayer]);



  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (abortController.current) {
        abortController.current.abort();
      }
      
      // Clean up all layers on unmount
      ['township', 'range', 'grid', 'sections', 'quarter-sections', 'subdivisions'].forEach(layer => {
        try {
          const layerId = `container-${layer}`;
          const sourceId = `container-${layer}-source`;
          const labelLayerId = `${layerId}-labels`;
          
          if (map?.getLayer?.(layerId)) {
            map.removeLayer(layerId);
          }
          if (map?.getSource?.(sourceId)) {
            map.removeSource(sourceId);
          }
          
          // Clean up label layers
          if (map?.getLayer?.(labelLayerId)) {
            map.removeLayer(labelLayerId);
          }
          if (map?.getSource?.(labelLayerId)) {
            map.removeSource(labelLayerId);
          }
        } catch (error) {
          // Ignore cleanup errors
        }
      });
      
      // Remove all HTML label overlays to prevent memory leaks
      try {
        const allLabelOverlays = document.querySelectorAll('[data-label-layer]');
        allLabelOverlays.forEach(overlay => overlay.remove());
      } catch (error) {
        // Ignore cleanup errors
      }
      
      // Clear cached references to prevent memory leaks
      if ((window as any)._cachedSidePanel) {
        (window as any)._cachedSidePanel = null;
      }
      if ((map as any)._lastZoomLevel) {
        (map as any)._lastZoomLevel = null;
      }
    };
  }, [map]);

  // 🏷️ RENDER CONTAINER LABEL MANAGERS
  return (
    <>
      {/* Render label managers for each active layer */}
      {Array.from(activeLayers).map(layer => {
        const features = layerData.get(layer) || [];
        const color = getLayerColor(layer);
        
        // Create label options from overlay state
        const labelOptions: ContainerLabelOptions = {
          showGridLabels: overlayState.showGridLabels,
          showTownshipLabels: overlayState.showTownshipLabels,
          showRangeLabels: overlayState.showRangeLabels,
          showSectionLabels: overlayState.showSectionLabels,
          showQuarterSectionLabels: overlayState.showQuarterSectionLabels,
          showSubdivisionLabels: overlayState.showSubdivisionLabels,
        };
        
        return (
          <ContainerLabelManager
            key={`label-${layer}`}
            map={map}
            layerId={`container-${layer}`}
            features={features}
            layerType={layer}
            color={color}
            options={labelOptions}
            onLabelsCreated={(labelFeatures) => {
              console.log(`✅ Labels created for ${layer}: ${labelFeatures.length} features`);
            }}
          />
        );
      })}
    </>
  );
};
