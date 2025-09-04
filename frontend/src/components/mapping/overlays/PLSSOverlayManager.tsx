/**
 * PLSS Overlay Manager
 * Clean, container-only implementation using modular architecture
 * Handles container-based PLSS overlays with dedicated components
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useMapContext } from '../core/MapContext';
import ContainerOverlayManager, { ContainerOverlayState } from './ContainerOverlayManager';
import ContainerOverlayControls from './ContainerOverlayControls';
import { plssCache } from '../../services/plss';

export interface PLSSOverlayManagerProps {
  stateName: string;
  schemaData?: any;
  containerBounds?: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
  className?: string;
}

export const PLSSOverlayManager: React.FC<PLSSOverlayManagerProps> = ({
  stateName,
  schemaData,
  containerBounds,
  className = '',
}) => {
  const { map } = useMapContext();
  
  // Container overlay state
  const [containerOverlayState, setContainerOverlayState] = useState<ContainerOverlayState>({
    showTownship: false,
    showRange: false,
    showGrid: false,
    showSections: false,
    showQuarterSections: false,
  });

  // Loading and error states
  const [loadingLayers, setLoadingLayers] = useState<Set<string>>(new Set());
  const [layerErrors, setLayerErrors] = useState<Map<string, string>>(new Map());
  const [loadedFeatures, setLoadedFeatures] = useState<Map<string, any[]>>(new Map());

  // Handle overlay load
  const handleOverlayLoad = useCallback((layer: string, features: any[], fullResult?: any) => {
    console.log(`✅ Container overlay loaded: ${layer} with ${features.length} features`);
    console.log(`📦 Full result available:`, !!fullResult);
    if (fullResult) {
      console.log(`📊 Full result structure:`, Object.keys(fullResult));
    }
    setLoadedFeatures(prev => new Map(prev).set(layer, features));

    // Cache PLSS sections for efficient snap detection
    if (layer === 'sections' && fullResult) {
      console.log(`💾 Attempting to cache PLSS sections...`);
      plssCache.storeSections(fullResult);
      const status = plssCache.getCacheStatus();
      console.log(`📈 Cache status after storing: ${status.totalEntries} entries, ${status.totalSections} sections`);
    } else {
      console.log(`⚠️ Not caching: layer=${layer}, hasFullResult=${!!fullResult}`);
    }
  }, []);

  // Handle overlay error
  const handleOverlayError = useCallback((layer: string, error: string) => {
    console.error(`❌ Container overlay error: ${layer} - ${error}`);
    setLayerErrors(prev => new Map(prev).set(layer, error));
  }, []);

  // Handle overlay unload
  const handleOverlayUnload = useCallback((layer: string) => {
    console.log(`🗑️ Container overlay unloaded: ${layer}`);
    setLoadedFeatures(prev => {
      const newMap = new Map(prev);
      newMap.delete(layer);
      return newMap;
    });
    setLayerErrors(prev => {
      const newMap = new Map(prev);
      newMap.delete(layer);
      return newMap;
    });
  }, []);

  // Handle overlay state change
  const handleOverlayStateChange = useCallback((newState: ContainerOverlayState) => {
    console.log('🔄 Container overlay state changed:', newState);
    setContainerOverlayState(newState);
  }, []);

  // Validate required data
  const hasRequiredData = schemaData && containerBounds && stateName;

  if (!map) {
    return (
      <div className={`plss-overlay-manager ${className}`}>
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
          <p className="text-sm text-yellow-800">⚠️ Map not available</p>
        </div>
      </div>
    );
  }

  if (!hasRequiredData) {
    return (
      <div className={`plss-overlay-manager ${className}`}>
        <div className="bg-blue-50 border border-blue-200 rounded p-3">
          <p className="text-sm text-blue-800">
            📋 Waiting for parcel data...
          </p>
          <div className="text-xs text-blue-600 mt-1">
            {!schemaData && '• Schema data missing'}
            {!containerBounds && '• Container bounds missing'}
            {!stateName && '• State name missing'}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`plss-overlay-manager ${className}`}>
      {/* Container Overlay Controls */}
      <ContainerOverlayControls
        overlayState={containerOverlayState}
        onOverlayStateChange={handleOverlayStateChange}
        loadingLayers={loadingLayers}
        layerErrors={layerErrors}
        className="mb-4"
      />

      {/* Container Overlay Manager (logic-only component) */}
      <ContainerOverlayManager
        map={map}
        schemaData={schemaData}
        containerBounds={containerBounds}
        state={stateName}
        overlayState={containerOverlayState}
        onOverlayLoad={handleOverlayLoad}
        onOverlayError={handleOverlayError}
        onOverlayUnload={handleOverlayUnload}
      />

      {/* Status Display */}
      <div className="bg-gray-50 border border-gray-200 rounded p-3">
        <h4 className="text-sm font-medium text-gray-800 mb-2">📊 Status</h4>
        
        {/* Active Layers */}
        <div className="mb-2">
          <span className="text-xs text-gray-600">Active layers: </span>
          {Array.from(loadedFeatures.keys()).length > 0 ? (
            <span className="text-xs text-green-600">
              {Array.from(loadedFeatures.keys()).join(', ')}
            </span>
          ) : (
            <span className="text-xs text-gray-500">None</span>
          )}
        </div>

        {/* Feature Counts */}
        {Array.from(loadedFeatures.entries()).map(([layer, features]) => (
          <div key={layer} className="text-xs text-gray-600">
            {layer}: {features.length} features
          </div>
        ))}

        {/* Regional Overlay Notice */}
        <div className="mt-3 p-2 bg-blue-50 border border-blue-200 rounded">
          <p className="text-xs text-blue-800">
            🌍 Regional overlays coming soon...
          </p>
        </div>
      </div>
    </div>
  );
};

export default PLSSOverlayManager;

