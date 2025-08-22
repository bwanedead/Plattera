/**
 * Container PLSS Manager
 * Dedicated manager for container-based PLSS overlays
 * Clean, focused implementation for parcel-relative overlays
 */

import React, { useState } from 'react';
import { ContainerOverlayManager, ContainerOverlayState } from './ContainerOverlayManager';
import { ContainerOverlayControls } from './ContainerOverlayControls';
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
}

export const ContainerPLSSManager: React.FC<ContainerPLSSManagerProps> = ({
  map,
  schemaData,
  containerBounds,
  state,
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
        onOverlayLoad={(layer, features) => {
          console.log(`✅ Container overlay loaded: ${layer} with ${features.length} features`);
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
