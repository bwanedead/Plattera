/**
 * Container Overlay Manager
 * Dedicated manager for container-based PLSS overlays
 * Handles loading, unloading, and visibility of container overlays
 */

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { ContainerApi, ContainerLayer, ContainerRequest } from '../../../services/plss/containerApi';


export interface ContainerOverlayState {
  showGrid: boolean;
  showTownship: boolean;
  showRange: boolean;
  showSections: boolean;
  showQuarterSections: boolean;
  showSubdivisions: boolean;
  // Label visibility states
  showGridLabels: boolean;
  showTownshipLabels: boolean;
  showRangeLabels: boolean;
  showSectionLabels: boolean;
  showQuarterSectionLabels: boolean;
  showSubdivisionLabels: boolean;
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

  // Add label layers to map
  const addLabelLayer = useCallback((layerId: string, features: any[], color: string) => {
    console.log(`🚀 Starting label layer creation for ${layerId}`);
    console.log(`📊 Input features: ${features.length}`);
    console.log(`🎨 Label color: ${color}`);
    
    if (!map) {
      console.log('❌ Map not available for label layer');
      return;
    }
    
    const labelLayerId = `${layerId}-labels`;
    
    // Remove existing label layer if it exists
    if (map.getLayer(labelLayerId)) {
      map.removeLayer(labelLayerId);
    }
    if (map.getSource(labelLayerId)) {
      map.removeSource(labelLayerId);
    }
    
    // Create multiple label points along feature boundaries with offset
    const labelFeatures: any[] = [];
    features.forEach(feature => {
      console.log('🔍 Feature properties:', feature.properties);
      const label = feature.properties.label || feature.properties.display_label || 'Label';
      console.log('🏷️ Using label:', label);
      const coordinates = feature.geometry.coordinates[0];
      
      // Create multiple label points along the boundary with offset
      const numLabels = Math.min(6, Math.floor(coordinates.length / 3)); // More labels for better coverage
      for (let i = 0; i < numLabels; i++) {
        const index = Math.floor((i + 1) * coordinates.length / (numLabels + 1));
        const coord = coordinates[index];
        
        // Calculate offset perpendicular to the boundary
        const prevIndex = (index - 1 + coordinates.length) % coordinates.length;
        const nextIndex = (index + 1) % coordinates.length;
        
        const prevCoord = coordinates[prevIndex];
        const nextCoord = coordinates[nextIndex];
        
        // Calculate direction vector
        const dx = nextCoord[0] - prevCoord[0];
        const dy = nextCoord[1] - prevCoord[1];
        const length = Math.sqrt(dx * dx + dy * dy);
        
        // Normalize and create perpendicular vector (offset direction)
        if (length > 0) {
          const offsetDistance = 0.0001; // Small offset in degrees
          const perpX = -dy / length * offsetDistance;
          const perpY = dx / length * offsetDistance;
          
          // Create offset point
          const offsetCoord = [coord[0] + perpX, coord[1] + perpY];
          
          labelFeatures.push({
            type: 'Feature',
            geometry: {
              type: 'Point',
              coordinates: offsetCoord
            },
            properties: {
              label: label,
              angle: Math.atan2(dy, dx) * 180 / Math.PI
            }
          });
        }
      }
    });
    
    console.log('📝 Created label features:', labelFeatures.length);
    
    // Add label source
    map.addSource(labelLayerId, {
      type: 'geojson',
      data: {
        type: 'FeatureCollection',
        features: labelFeatures
      }
    });
    
    // Use a simple circle layer instead of text to avoid glyphs requirement
    console.log(`🎯 Creating circle markers for ${labelLayerId}`);
    
    // Add a simple circle layer to show label positions
    map.addLayer({
      id: labelLayerId,
      type: 'circle',
      source: labelLayerId,
      paint: {
        'circle-radius': 8,
        'circle-color': color,
        'circle-stroke-color': 'white',
        'circle-stroke-width': 2,
        'circle-opacity': 0.8
      }
    });
    
    console.log(`✅ Created circle markers for ${labelLayerId} with ${labelFeatures.length} points`);
    
    console.log(`🎨 Label color: ${color}`);
    console.log(`📝 Final label features: ${labelFeatures.length}`);
    
    // Verify the layer was actually added
    setTimeout(() => {
      if (map.getLayer(labelLayerId)) {
        console.log(`✅ Confirmed: Label layer ${labelLayerId} exists on map`);
      } else {
        console.log(`❌ ERROR: Label layer ${labelLayerId} was not added to map`);
      }
    }, 100);
  }, [map]);

  // Determine which layers should be active based on overlay state
  const getDesiredLayers = useCallback((): ContainerLayer[] => {
    const layers: ContainerLayer[] = [];
    
    if (overlayState.showGrid) layers.push('grid');
    if (overlayState.showTownship) layers.push('township');
    if (overlayState.showRange) layers.push('range');
    if (overlayState.showSections) layers.push('sections');
    if (overlayState.showQuarterSections) layers.push('quarter-sections');
    if (overlayState.showSubdivisions) layers.push('subdivisions');
    
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
  }, [overlayState, getDesiredLayers, loadLayer, unloadLayer, activeLayers, loadingLayers]);

  // Handle label visibility changes
  useEffect(() => {
    if (!map) return;
    
    console.log('🔄 Label visibility changed:', {
      showGridLabels: overlayState.showGridLabels,
      showTownshipLabels: overlayState.showTownshipLabels,
      showRangeLabels: overlayState.showRangeLabels,
      showSectionLabels: overlayState.showSectionLabels,
      showQuarterSectionLabels: overlayState.showQuarterSectionLabels,
      showSubdivisionLabels: overlayState.showSubdivisionLabels
    });
    
    // Check each layer for label visibility
    const labelStates = [
      { layer: 'grid', show: overlayState.showGridLabels },
      { layer: 'township', show: overlayState.showTownshipLabels },
      { layer: 'range', show: overlayState.showRangeLabels },
      { layer: 'sections', show: overlayState.showSectionLabels },
      { layer: 'quarter-sections', show: overlayState.showQuarterSectionLabels },
      { layer: 'subdivisions', show: overlayState.showSubdivisionLabels }
    ];
    
    labelStates.forEach(({ layer, show }) => {
      const layerId = `container-${layer}`;
      const labelLayerId = `${layerId}-labels`;
      
      console.log(`🎯 Processing label for ${layer}:`, { show, hasData: layerData.has(layer as ContainerLayer) });
      
      if (show && layerData.has(layer as ContainerLayer)) {
        // Add label layer
        const features = layerData.get(layer as ContainerLayer) || [];
        const color = getLayerColor(layer as ContainerLayer);
        console.log(`✅ Adding label layer for ${layer} with ${features.length} features`);
        addLabelLayer(layerId, features, color);
      } else {
        // Remove label layer
        if (map.getLayer(labelLayerId)) {
          console.log(`🗑️ Removing label layer for ${layer}`);
          map.removeLayer(labelLayerId);
        }
        if (map.getSource(labelLayerId)) {
          map.removeSource(labelLayerId);
        }
      }
    });
  }, [map, overlayState, layerData, addLabelLayer, getLayerColor]);

  // Cleanup on unmount only
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
