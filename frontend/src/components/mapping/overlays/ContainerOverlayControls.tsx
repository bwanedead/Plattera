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
        return '⏳';
      case 'error':
        return '❌';
      case 'ready':
        return '✅';
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
      <div className="bg-white rounded-lg shadow-sm border border-gray-200">
        <h3 className="text-lg font-semibold mb-3 text-gray-800 px-4 pt-4">
          Container Overlays
        </h3>
        
        <div className="space-y-3 px-4 pb-4">
          {/* Grid Control */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="showGrid"
                checked={overlayState.showGrid}
                onChange={() => handleToggle('showGrid')}
                className="w-4 h-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500"
              />
              <label htmlFor="showGrid" className="text-sm font-medium text-gray-700">
                Grid (Township + Range Cell)
              </label>
            </div>
            <span className={`text-xs ${getStatusColor('grid')}`}>
              {getStatusIcon('grid')}
            </span>
          </div>

          {/* Township Control */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="showTownship"
                checked={overlayState.showTownship}
                onChange={() => handleToggle('showTownship')}
                disabled={overlayState.showGrid}
                className="w-4 h-4 text-red-600 border-gray-300 rounded focus:ring-red-500 disabled:opacity-50"
              />
              <label htmlFor="showTownship" className="text-sm font-medium text-gray-700">
                Township Lines
              </label>
            </div>
            <span className={`text-xs ${getStatusColor('township')}`}>
              {getStatusIcon('township')}
            </span>
          </div>

          {/* Range Control */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="showRange"
                checked={overlayState.showRange}
                onChange={() => handleToggle('showRange')}
                disabled={overlayState.showGrid}
                className="w-4 h-4 text-green-600 border-gray-300 rounded focus:ring-green-500 disabled:opacity-50"
              />
              <label htmlFor="showRange" className="text-sm font-medium text-gray-700">
                Range Lines
              </label>
            </div>
            <span className={`text-xs ${getStatusColor('range')}`}>
              {getStatusIcon('range')}
            </span>
          </div>

          {/* Sections Control */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="showSections"
                checked={overlayState.showSections}
                onChange={() => handleToggle('showSections')}
                className="w-4 h-4 text-yellow-600 border-gray-300 rounded focus:ring-yellow-500"
              />
              <label htmlFor="showSections" className="text-sm font-medium text-gray-700">
                Sections
              </label>
            </div>
            <span className={`text-xs ${getStatusColor('sections')}`}>
              {getStatusIcon('sections')}
            </span>
          </div>

          {/* Quarter Sections Control */}
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <input
                type="checkbox"
                id="showQuarterSections"
                checked={overlayState.showQuarterSections}
                onChange={() => handleToggle('showQuarterSections')}
                className="w-4 h-4 text-purple-600 border-gray-300 rounded focus:ring-purple-500"
              />
              <label htmlFor="showQuarterSections" className="text-sm font-medium text-gray-700">
                Quarter Sections
              </label>
            </div>
            <span className={`text-xs ${getStatusColor('quarter-sections')}`}>
              {getStatusIcon('quarter-sections')}
            </span>
          </div>
        </div>

        {/* Error Display */}
        {Array.from(layerErrors.entries()).length > 0 && (
          <div className="mt-3 mx-4 mb-4 p-2 bg-red-50 border border-red-200 rounded">
            <h4 className="text-sm font-medium text-red-800 mb-1">Errors:</h4>
            {Array.from(layerErrors.entries()).map(([layer, error]) => (
              <div key={layer} className="text-xs text-red-700">
                <strong>{layer}:</strong> {error}
              </div>
            ))}
          </div>
        )}

        {/* Info */}
        <div className="px-4 pb-4 text-xs text-gray-500 border-t border-gray-100 pt-3">
          <p>Container overlays show features relative to your parcel</p>
          <p>Grid shows the specific township-range cell</p>
        </div>
      </div>
    </div>
  );
};

export default ContainerOverlayControls;
