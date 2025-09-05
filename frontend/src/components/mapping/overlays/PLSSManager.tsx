/**
 * Main PLSS Manager
 * Orchestrates container and regional PLSS overlay managers
 * Clean, organized architecture with clear separation of concerns
 */

import React, { useState, useCallback } from 'react';
import { ContainerPLSSManager } from './ContainerPLSSManager';
import RegionalPLSSManager from './RegionalPLSSManager';
import { useMapContext } from '../core/MapContext';
import { plssCache } from '../../../services/plss/coordinateApi';

export type PLSSMode = 'container' | 'regional';

export interface PLSSManagerProps {
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

export const PLSSManager: React.FC<PLSSManagerProps> = ({
  stateName,
  schemaData,
  containerBounds,
  className = '',
}) => {
  const { map } = useMapContext();
  const [mode, setMode] = useState<PLSSMode>('container');

  const handleModeChange = useCallback((newMode: PLSSMode) => {
    console.log(`🔄 PLSS mode changed from ${mode} to ${newMode}`);
    setMode(newMode);
  }, [mode]);

  const handleOverlayLoad = useCallback((layer: string, features: any[], fullResult?: any) => {
    console.log(`📦 PLSS overlay loaded: ${layer} with ${features.length} features`);

    // Store sections in cache when sections layer is loaded
    if (layer === 'sections' && fullResult) {
      console.log('💾 Storing sections in PLSS cache');
      plssCache.storeSections(fullResult);
      const cacheStatus = plssCache.getCacheStatus();
      console.log(`📊 Cache status after storing: ${cacheStatus.totalEntries} entries, ${cacheStatus.totalSections} sections`);
    }
  }, []);

  return (
    <div className={`plss-manager ${className}`}>
      {/* Mode Selector */}
      <div className="flex space-x-1 mb-4">
        <button
          onClick={() => handleModeChange('container')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
            mode === 'container'
              ? 'bg-blue-600 text-white shadow-lg'
              : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
          }`}
        >
          Container
        </button>
        <button
          onClick={() => handleModeChange('regional')}
          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
            mode === 'regional'
              ? 'bg-blue-600 text-white shadow-lg'
              : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
          }`}
        >
          Regional
        </button>
      </div>

      {/* Container Manager */}
      {mode === 'container' && map && (
        <ContainerPLSSManager
          map={map}
          state={stateName}
          schemaData={schemaData}
          containerBounds={containerBounds}
          onOverlayLoad={handleOverlayLoad}
        />
      )}

      {/* Regional Manager */}
      {mode === 'regional' && (
        <RegionalPLSSManager
          stateName={stateName}
        />
      )}
    </div>
  );
};

export default PLSSManager;
