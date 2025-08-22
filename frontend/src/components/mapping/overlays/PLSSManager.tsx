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
      <div className="bg-gray-900 rounded-xl shadow-lg border border-gray-700 backdrop-blur-sm mb-4">
        <h3 className="text-lg font-semibold mb-4 text-white px-6 pt-6 tracking-wide">
          PLSS Overlays
        </h3>
        
        <div className="flex space-x-1 px-6 pb-6">
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

        {/* Mode Description */}
        <div className="px-6 pb-6 text-xs text-gray-400 border-t border-gray-700 pt-4 font-mono">
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
