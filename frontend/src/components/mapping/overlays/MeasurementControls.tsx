/**
 * Measurement Controls
 * UI controls for measurement tools
 */

import React from 'react';
import { MeasurementMode, MeasurementState, CardinalDirection } from '../../../hooks/useMeasurementState';
import { Measurement } from '../../../utils/measurementUtils';
import { formatDistance, formatBearing, directionToBearing } from '../../../utils/measurementUtils';
import { SidePanelSection } from '../panels/SidePanel';

interface MeasurementControlsProps {
  measurementState: MeasurementState;
  onModeChange: (mode: MeasurementMode) => void;
  onToggleSnapping: () => void;
  onToggleCoordinates: () => void;
  onDirectDistanceChange: (distance: string) => void;
  onDirectBearingChange: (bearing: string) => void;
  onSelectedDirectionChange: (direction: CardinalDirection) => void;
  onCreateDirectMeasurement: () => void;
  onToggleMeasurementVisibility: (measurementId: string) => void;
  onRemoveMeasurement: (measurementId: string) => void;
  onClearAllMeasurements: () => void;
  onHideSnapFeedback: () => void;
  onChainFromMeasurement: (measurementId: string) => void;
}

export const MeasurementControls: React.FC<MeasurementControlsProps> = ({
  measurementState,
  onModeChange,
  onToggleSnapping,
  onToggleCoordinates,
  onDirectDistanceChange,
  onDirectBearingChange,
  onSelectedDirectionChange,
  onCreateDirectMeasurement,
  onToggleMeasurementVisibility,
  onRemoveMeasurement,
  onClearAllMeasurements,
  onHideSnapFeedback,
  onChainFromMeasurement,
}) => {
  const {
    mode,
    snappingEnabled,
    showCoordinates,
    measurements,
    currentMeasurement,
    directDistance,
    directBearing,
    selectedDirection,
    directStartPoint,
    snapFeedback
  } = measurementState;

  const cardinalDirections: CardinalDirection[] = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];

  return (
    <SidePanelSection title="Measurement Tools">
      <div className="space-y-4">
        {/* Mode Selection */}
        <div className="space-y-2">
          <div className="flex space-x-1">
            <button
              onClick={() => onModeChange('disabled')}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex-1 ${
                mode === 'disabled'
                  ? 'bg-gray-600 text-white shadow-lg'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
            >
              Disabled
            </button>
            <button
              onClick={() => onModeChange('click-drag')}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex-1 ${
                mode === 'click-drag'
                  ? 'bg-blue-600 text-white shadow-lg'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
            >
              Click & Drag
            </button>
            <button
              onClick={() => onModeChange('direct-input')}
              className={`px-3 py-2 rounded-lg text-sm font-medium transition-all duration-200 flex-1 ${
                mode === 'direct-input'
                  ? 'bg-blue-600 text-white shadow-lg'
                  : 'bg-gray-800 text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
            >
              Direct Input
            </button>
          </div>
        </div>

        {/* Snapping Toggle */}
        <div className="flex items-center space-x-3">
          <input
            type="checkbox"
            id="plss-snapping"
            checked={snappingEnabled}
            onChange={onToggleSnapping}
            className="w-4 h-4 text-blue-600 bg-gray-800 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
          />
          <label
            htmlFor="plss-snapping"
            className="text-sm font-medium text-gray-300 cursor-pointer select-none"
          >
            Enable PLSS Snapping
          </label>
          {snappingEnabled && (
            <div className="flex items-center space-x-2">
              <span className="text-green-400 text-xs font-semibold">🧲 ACTIVE</span>
              <div className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></div>
            </div>
          )}
          {!snappingEnabled && (
            <span className="text-gray-500 text-xs">⚪ DISABLED</span>
          )}
        </div>

        {/* Snap Feedback */}
        {snapFeedback && snapFeedback.isVisible && (
          <div className="bg-green-900/30 border border-green-600/50 rounded-lg p-3 animate-pulse">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium text-green-300 flex items-center">
                🧲 SNAPPED!
                <button
                  onClick={onHideSnapFeedback}
                  className="ml-2 text-gray-400 hover:text-gray-300 text-xs"
                  title="Hide feedback"
                >
                  ✕
                </button>
              </div>
            </div>
            <div className="text-sm text-green-200 space-y-1">
              <div className="font-semibold">{snapFeedback.featureName}</div>
              <div className="text-xs opacity-80">
                Coordinates: {snapFeedback.coordinates.lat.toFixed(4)}, {snapFeedback.coordinates.lng.toFixed(4)}
              </div>
            </div>
          </div>
        )}

        {/* Quick Snap Notification */}
        {snapFeedback && !snapFeedback.isVisible && (
          <div className="bg-green-900/20 border border-green-600/30 rounded-lg px-3 py-2">
            <div className="text-xs text-green-300 flex items-center">
              <span className="mr-1">⚡</span>
              Last snap: <span className="font-medium ml-1">{snapFeedback.featureName}</span>
            </div>
          </div>
        )}

        {/* Coordinate Display Toggle */}
        <div className="flex items-center space-x-3">
          <input
            type="checkbox"
            id="coordinate-display"
            checked={showCoordinates}
            onChange={onToggleCoordinates}
            className="w-4 h-4 text-blue-600 bg-gray-800 border-gray-600 rounded focus:ring-blue-500 focus:ring-2"
          />
          <label
            htmlFor="coordinate-display"
            className="text-sm font-medium text-gray-300 cursor-pointer select-none"
          >
            Show Coordinates
          </label>
          {showCoordinates && (
            <div className="flex items-center space-x-2">
              <span className="text-blue-400 text-xs font-semibold">📍 VISIBLE</span>
              <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
            </div>
          )}
          {!showCoordinates && (
            <span className="text-gray-500 text-xs">🙈 HIDDEN</span>
          )}
        </div>

        {/* Click & Drag Status */}
        {mode === 'click-drag' && currentMeasurement.length === 1 && (
          <div className="text-sm text-yellow-400 bg-yellow-900/20 px-3 py-2 rounded-lg">
            Click second point to complete measurement
          </div>
        )}

        {/* Direct Input Form */}
        {mode === 'direct-input' && (
          <div className="space-y-3">
            <div className="text-sm text-gray-300">
              {!directStartPoint ? 'Click on map to set start point' : 'Start point set - enter distance and bearing'}
            </div>

            <div className="space-y-3">
              <div>
                <label className="block text-xs text-gray-400 mb-1">Distance (ft)</label>
                <input
                  type="number"
                  value={directDistance}
                  onChange={(e) => onDirectDistanceChange(e.target.value)}
                  placeholder="1000"
                  className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Direction</label>
                  <select
                    value={selectedDirection}
                    onChange={(e) => onSelectedDirectionChange(e.target.value as CardinalDirection)}
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
                  >
                    {cardinalDirections.map((direction) => (
                      <option key={direction} value={direction}>
                        {direction} ({directionToBearing(direction)}°)
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">Bearing (°)</label>
                  <input
                    type="number"
                    value={directBearing}
                    onChange={(e) => onDirectBearingChange(e.target.value)}
                    placeholder="45"
                    min="0"
                    max="360"
                    step="0.1"
                    className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white text-sm focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="text-xs text-gray-400 bg-gray-800/50 px-3 py-2 rounded">
                Using: {directBearing ? `${directBearing}° (Custom)` : `${directionToBearing(selectedDirection)}° ${selectedDirection}`}
              </div>
            </div>

            <button
              onClick={onCreateDirectMeasurement}
              disabled={!directStartPoint || !directDistance || (!directBearing && selectedDirection === 'N')}
              className="w-full px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors duration-200"
            >
              Create Measurement
            </button>
          </div>
        )}

        {/* Measurements List */}
        {measurements.length > 0 && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-gray-300">Measurements</h4>
              <button
                onClick={onClearAllMeasurements}
                className="text-xs text-red-400 hover:text-red-300"
              >
                Clear All
              </button>
            </div>

            <div className="max-h-40 overflow-y-auto space-y-1">
              {measurements.map((measurement) => (
                <div key={measurement.id} className="bg-gray-800/50 px-3 py-2 rounded text-sm space-y-1">
                  <div className="flex items-center justify-between">
                    <div className="flex-1 min-w-0">
                      <div className="text-white font-medium truncate">
                        {formatDistance(measurement.distance)}
                      </div>
                      {measurement.bearing && (
                        <div className="text-gray-400 text-xs truncate">
                          {formatBearing(measurement.bearing)}
                        </div>
                      )}
                    </div>
                    <div className="flex items-center space-x-2 ml-2">
                      <button
                        onClick={() => onToggleMeasurementVisibility(measurement.id)}
                        className="text-gray-400 hover:text-white text-sm"
                        title={measurement.isVisible ? 'Hide measurement' : 'Show measurement'}
                      >
                        {measurement.isVisible ? '👁️' : '🙈'}
                      </button>
                      <button
                        onClick={() => onChainFromMeasurement(measurement.id)}
                        className="text-gray-400 hover:text-blue-400 text-sm"
                        title="Chain from end point"
                      >
                        🔗
                      </button>
                      <button
                        onClick={() => onRemoveMeasurement(measurement.id)}
                        className="text-gray-400 hover:text-red-400 text-sm"
                        title="Remove measurement"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>

                  {/* Coordinate display when enabled */}
                  {showCoordinates && measurement.points.length >= 2 && (
                    <div className="border-t border-gray-700 pt-2 space-y-1">
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        <div>
                          <div className="text-blue-300 font-medium">START:</div>
                          <div className="text-gray-300 font-mono">
                            {measurement.points[0].lat.toFixed(4)}, {measurement.points[0].lng.toFixed(4)}
                          </div>
                          {measurement.points[0].snappedFeature && (
                            <div className="text-green-400 text-xs">
                              🧲 {measurement.points[0].snappedFeature}
                            </div>
                          )}
                        </div>
                        <div>
                          <div className="text-orange-300 font-medium">END:</div>
                          <div className="text-gray-300 font-mono">
                            {measurement.points[1].lat.toFixed(4)}, {measurement.points[1].lng.toFixed(4)}
                          </div>
                          {measurement.points[1].snappedFeature && (
                            <div className="text-green-400 text-xs">
                              🧲 {measurement.points[1].snappedFeature}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Help Text */}
        <div className="text-xs text-gray-500 bg-gray-900/50 px-3 py-2 rounded-lg">
          {mode === 'disabled' && 'Enable measurement tools to start measuring distances and bearings on the map.'}
          {mode === 'click-drag' && 'Click two points on the map to measure the distance between them.'}
          {mode === 'direct-input' && 'Click to set a start point, then enter distance and bearing to create a measurement.'}
        </div>
      </div>
    </SidePanelSection>
  );
};
