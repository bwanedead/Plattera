/**
 * Container Overlay Controls
 * Dedicated controls for container-based PLSS overlays
 * Clean, focused UI for parcel-relative overlay management
 */

import React from 'react';
import { ContainerOverlayState } from './ContainerOverlayManager';

interface ContainerOverlayControlsProps {
  overlayState: ContainerOverlayState;
  onOverlayStateChange: (newState: ContainerOverlayState) => void;
  loadingLayers?: Set<string>;
  layerErrors?: Map<string, string>;
  className?: string;
}

export const ContainerOverlayControls: React.FC<ContainerOverlayControlsProps> = ({
  overlayState,
  onOverlayStateChange,
  loadingLayers = new Set(),
  layerErrors = new Map(),
  className = '',
}) => {
  const handleToggle = (key: keyof ContainerOverlayState) => {
    const newState = { ...overlayState };
    newState[key] = !newState[key];
    
    // Special logic for grid vs township/range
    if (key === 'showGrid') {
      if (newState.showGrid) {
        // When grid is enabled, disable individual township/range
        newState.showTownship = false;
        newState.showRange = false;
      }
    } else if (key === 'showTownship' || key === 'showRange') {
      // When individual layers are enabled, disable grid
      newState.showGrid = false;
    }
    
    onOverlayStateChange(newState);
  };

  const getLayerStatus = (layer: string) => {
    if (loadingLayers.has(layer)) {
      return 'loading';
    }
    if (layerErrors.has(layer)) {
      return 'error';
    }
    return 'ready';
  };

  const getStatusIcon = (layer: string) => {
    const status = getLayerStatus(layer);
    switch (status) {
      case 'loading':
        return '⋯';
      case 'error':
        return '!';
      case 'ready':
        return '✓';
      default:
        return '';
    }
  };

  const getStatusColor = (layer: string) => {
    const status = getLayerStatus(layer);
    switch (status) {
      case 'loading':
        return 'text-blue-500';
      case 'error':
        return 'text-red-500';
      case 'ready':
        return 'text-green-500';
      default:
        return 'text-gray-500';
    }
  };

  return (
    <div className={`container-overlay-controls ${className}`}>
      <div className="bg-gray-900 rounded-xl shadow-lg border border-gray-700 backdrop-blur-sm">
        <h3 className="text-lg font-semibold mb-4 text-white px-6 pt-6 tracking-wide">
          PLSS Overlays
        </h3>
        
        <div className="space-y-4 px-6 pb-6">
          {/* Grid Control */}
          <div className="flex items-center py-3 border-b border-gray-700">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="showGrid"
                checked={overlayState.showGrid}
                onChange={() => handleToggle('showGrid')}
                className="w-5 h-5 text-blue-500 border-gray-600 rounded-md focus:ring-blue-500 focus:ring-2 bg-gray-800"
              />
              <label htmlFor="showGrid" className="text-sm font-medium text-gray-200 tracking-wide">
                Grid (Township + Range Cell)
              </label>
            </div>
          </div>

          {/* Township Control */}
          <div className="flex items-center py-3 border-b border-gray-700">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="showTownship"
                checked={overlayState.showTownship}
                onChange={() => handleToggle('showTownship')}
                disabled={overlayState.showGrid}
                className="w-5 h-5 text-red-500 border-gray-600 rounded-md focus:ring-red-500 focus:ring-2 bg-gray-800 disabled:opacity-40"
              />
              <label htmlFor="showTownship" className="text-sm font-medium text-gray-200 tracking-wide">
                Township Lines
              </label>
            </div>
          </div>

          {/* Range Control */}
          <div className="flex items-center py-3 border-b border-gray-700">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="showRange"
                checked={overlayState.showRange}
                onChange={() => handleToggle('showRange')}
                disabled={overlayState.showGrid}
                className="w-5 h-5 text-green-500 border-gray-600 rounded-md focus:ring-green-500 focus:ring-2 bg-gray-800 disabled:opacity-40"
              />
              <label htmlFor="showRange" className="text-sm font-medium text-gray-200 tracking-wide">
                Range Lines
              </label>
            </div>
          </div>

          {/* Sections Control */}
          <div className="flex items-center py-3 border-b border-gray-700">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="showSections"
                checked={overlayState.showSections}
                onChange={() => handleToggle('showSections')}
                className="w-5 h-5 text-yellow-500 border-gray-600 rounded-md focus:ring-yellow-500 focus:ring-2 bg-gray-800"
              />
              <label htmlFor="showSections" className="text-sm font-medium text-gray-200 tracking-wide">
                Sections
              </label>
            </div>
          </div>

          {/* Quarter Sections Control */}
          <div className="flex items-center py-3 border-b border-gray-700">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="showQuarterSections"
                checked={overlayState.showQuarterSections}
                onChange={() => handleToggle('showQuarterSections')}
                className="w-5 h-5 text-purple-500 border-gray-600 rounded-md focus:ring-purple-500 focus:ring-2 bg-gray-800"
              />
              <label htmlFor="showQuarterSections" className="text-sm font-medium text-gray-200 tracking-wide">
                Quarter Sections
              </label>
            </div>
          </div>

          {/* Subdivisions Control */}
          <div className="flex items-center py-3 border-b border-gray-700">
            <div className="flex items-center space-x-3">
              <input
                type="checkbox"
                id="showSubdivisions"
                checked={overlayState.showSubdivisions}
                onChange={() => handleToggle('showSubdivisions')}
                className="w-5 h-5 text-indigo-500 border-gray-600 rounded-md focus:ring-indigo-500 focus:ring-2 bg-gray-800"
              />
              <label htmlFor="showSubdivisions" className="text-sm font-medium text-gray-200 tracking-wide">
                Subdivisions
              </label>
            </div>
          </div>
        </div>

        {/* Error Display */}
        {Array.from(layerErrors.entries()).length > 0 && (
          <div className="mt-4 mx-6 mb-4 p-3 bg-red-900/20 border border-red-700/30 rounded-lg">
            <h4 className="text-sm font-medium text-red-300 mb-2">Errors:</h4>
            {Array.from(layerErrors.entries()).map(([layer, error]) => (
              <div key={layer} className="text-xs text-red-400 font-mono">
                <strong>{layer}:</strong> {error}
              </div>
            ))}
          </div>
        )}

        {/* Info */}
        <div className="px-6 pb-6 text-xs text-gray-400 border-t border-gray-700 pt-4 font-mono">
          <p>Container overlays show features relative to your parcel</p>
          <p>Grid shows the specific township-range cell</p>
        </div>
      </div>
    </div>
  );
};

export default ContainerOverlayControls;
