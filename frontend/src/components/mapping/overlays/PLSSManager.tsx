/**
 * Main PLSS Manager
 * Orchestrates container and regional PLSS overlay managers
 * Clean, organized architecture with clear separation of concerns
 */

import React, { useState, useCallback } from 'react';
import ContainerPLSSManager from './ContainerPLSSManager';
import RegionalPLSSManager from './RegionalPLSSManager';

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
  const [mode, setMode] = useState<PLSSMode>('container');

  const handleModeChange = useCallback((newMode: PLSSMode) => {
    console.log(`🔄 PLSS mode changed from ${mode} to ${newMode}`);
    setMode(newMode);
  }, [mode]);

  return (
    <div className={`plss-manager ${className}`}>
      {/* Mode Selector */}
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 mb-4">
        <h3 className="text-lg font-semibold mb-3 text-gray-800 px-4 pt-4">
          PLSS Overlays
        </h3>
        
        <div className="flex space-x-2 px-4 pb-4">
          <button
            onClick={() => handleModeChange('container')}
            className={`px-3 py-2 rounded text-sm font-medium transition-colors ${
              mode === 'container'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Container
          </button>
          <button
            onClick={() => handleModeChange('regional')}
            className={`px-3 py-2 rounded text-sm font-medium transition-colors ${
              mode === 'regional'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
            }`}
          >
            Regional
          </button>
        </div>

        {/* Mode Description */}
        <div className="px-4 pb-4 text-xs text-gray-600 border-t border-gray-100 pt-3">
          {mode === 'container' ? (
            <p>Container overlays show features relative to your parcel</p>
          ) : (
            <p>Regional overlays show features for the entire map view</p>
          )}
        </div>
      </div>

      {/* Container Manager */}
      {mode === 'container' && (
        <ContainerPLSSManager
          stateName={stateName}
          schemaData={schemaData}
          containerBounds={containerBounds}
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
