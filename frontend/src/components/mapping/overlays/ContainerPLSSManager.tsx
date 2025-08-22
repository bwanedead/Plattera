/**
 * Container PLSS Manager
 * Dedicated manager for container-based PLSS overlays
 * Clean, focused implementation for parcel-relative overlays
 */

import React, { useState, useCallback } from 'react';
import { useMapContext } from '../core/MapContext';
import ContainerOverlayManager, { ContainerOverlayState } from './ContainerOverlayManager';
import ContainerOverlayControls from './ContainerOverlayControls';

export interface ContainerPLSSManagerProps {
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

export const ContainerPLSSManager: React.FC<ContainerPLSSManagerProps> = ({
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
    showSubdivisions: false,
  });

  // Loading and error states
  const [loadingLayers, setLoadingLayers] = useState<Set<string>>(new Set());
  const [layerErrors, setLayerErrors] = useState<Map<string, string>>(new Map());
  const [loadedFeatures, setLoadedFeatures] = useState<Map<string, any[]>>(new Map());

  // Handle overlay load
  const handleOverlayLoad = useCallback((layer: string, features: any[]) => {
    console.log(`✅ Container overlay loaded: ${layer} with ${features.length} features`);
    setLoadedFeatures(prev => new Map(prev).set(layer, features));
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
      <div className={`container-plss-manager ${className}`}>
        <div className="bg-yellow-50 border border-yellow-200 rounded p-3">
          <p className="text-sm text-yellow-800">Map not available</p>
        </div>
      </div>
    );
  }

  if (!hasRequiredData) {
    return (
      <div className={`container-plss-manager ${className}`}>
        <div className="bg-blue-50 border border-blue-200 rounded p-3">
          <p className="text-sm text-blue-800">
            Waiting for parcel data...
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
    <div className={`container-plss-manager ${className}`}>
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
      <div className="bg-gray-900 border border-gray-700 rounded-xl p-4">
        <h4 className="text-sm font-medium text-white mb-3 tracking-wide">Container Status</h4>
        
        {/* Active Layers */}
        <div className="mb-3">
          <span className="text-xs text-gray-400">Active layers: </span>
          {Array.from(loadedFeatures.keys()).length > 0 ? (
            <span className="text-xs text-green-400 font-mono">
              {Array.from(loadedFeatures.keys()).join(', ')}
            </span>
          ) : (
            <span className="text-xs text-gray-500 font-mono">None</span>
          )}
        </div>

        {/* Feature Counts */}
        {Array.from(loadedFeatures.entries()).map(([layer, features]) => (
          <div key={layer} className="text-xs text-gray-400 font-mono">
            {layer}: {features.length} features
          </div>
        ))}

        {/* Container Info */}
        <div className="mt-4 p-3 bg-green-900/20 border border-green-700/30 rounded-lg">
          <p className="text-xs text-green-300 font-mono">
            Container overlays show features relative to your parcel
          </p>
        </div>
      </div>
    </div>
  );
};

export default ContainerPLSSManager;
