/**
 * Container PLSS Manager
 * Dedicated manager for container-based PLSS overlays
 * Clean, focused implementation for parcel-relative overlays
 */

import React, { useState } from 'react';
import { ContainerOverlayManager } from './ContainerOverlayManager';
import { ContainerOverlayControls } from './ContainerOverlayControls';
import { ContainerOverlayState } from '../../../hooks/useContainerOverlayState';
import { useContainerOverlayState } from '../../../hooks/useContainerOverlayState';

interface ContainerPLSSManagerProps {
  map: any;
  schemaData?: any;
  containerBounds?: {
    west: number;
    south: number;
    east: number;
    north: number;
  };
  state?: string;
  onOverlayLoad?: (layer: string, features: any[], fullResult?: any) => void;
}

export const ContainerPLSSManager: React.FC<ContainerPLSSManagerProps> = ({
  map,
  schemaData,
  containerBounds,
  state,
  onOverlayLoad,
}) => {
  const { overlayState, setOverlayState, resetOverlays } = useContainerOverlayState();

  return (
    <div className="space-y-4">
      {/* Controls */}
      <ContainerOverlayControls
        overlayState={overlayState}
        onStateChange={setOverlayState}
      />

      {/* Overlay Manager */}
      <ContainerOverlayManager
        map={map}
        schemaData={schemaData}
        containerBounds={containerBounds}
        state={state}
        overlayState={overlayState}
        onOverlayLoad={(layer, features, fullResult) => {
          console.log(`✅ Container overlay loaded: ${layer} with ${features.length} features`);
          // Pass through to parent with fullResult for caching
          onOverlayLoad?.(layer, features, fullResult);
        }}
        onOverlayError={(layer, error) => {
          console.error(`❌ Container overlay failed: ${layer} - ${error}`);
        }}
        onOverlayUnload={(layer) => {
          console.log(`🔄 Container overlay unloaded: ${layer}`);
        }}
      />
    </div>
  );
};
