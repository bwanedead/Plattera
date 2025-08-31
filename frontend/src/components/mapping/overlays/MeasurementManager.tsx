/**
 * Measurement Manager
 * Main orchestrator for measurement tools
 * Coordinates controls, state, and overlay rendering
 */

import React, { useCallback, useEffect } from 'react';
import { useMapContext } from '../core/MapContext';
import { useMeasurementState, MeasurementMode } from '../../../hooks/useMeasurementState';
import { MeasurementControls } from './MeasurementControls';
import { MeasurementOverlay } from './MeasurementOverlay';
import {
  Measurement,
  MeasurementPoint,
  calculateDistance,
  calculateBearing,
  calculateEndPoint,
  findNearestPLSSFeature,
  generateMeasurementId,
  directionToBearing
} from '../../../utils/measurementUtils';
import type maplibregl from 'maplibre-gl';

interface MeasurementManagerProps {
  className?: string;
  stateName?: string;
}

export const MeasurementManager: React.FC<MeasurementManagerProps> = ({
  className = '',
  stateName = 'Wyoming',
}) => {
  const { map, isLoaded } = useMapContext();
  const {
    measurementState,
    setMode,
    toggleSnapping,
    setDirectDistance,
    setDirectBearing,
    setSelectedDirection,
    setDirectStartPoint,
    setSnapFeedback,
    hideSnapFeedback,
    addMeasurementPoint,
    resetCurrentMeasurement,
    addMeasurement,
    toggleMeasurementVisibility,
    removeMeasurement,
    clearAllMeasurements,
  } = useMeasurementState();

  // Draw persistent snap marker on map
  const drawSnapMarker = useCallback((point: MeasurementPoint) => {
    if (!map) {
      console.debug('⚠️ Cannot draw snap marker: map not available');
      return;
    }

    console.log(`🗺️ Drawing snap marker at ${point.lat.toFixed(6)}, ${point.lng.toFixed(6)}`);

    const snapId = 'measurement-snap-marker';
    const snapSourceId = `${snapId}-source`;

    // Remove existing snap marker
    try {
      if (map.getLayer(snapId)) map.removeLayer(snapId);
      if (map.getSource(snapSourceId)) map.removeSource(snapSourceId);
    } catch (error) {
      console.debug('Error removing snap marker:', error.message);
    }

    // Add new snap marker (persistent - will be managed by measurement state)
    try {
      map.addSource(snapSourceId, {
        type: 'geojson',
        data: {
          type: 'Feature',
          geometry: {
            type: 'Point',
            coordinates: [point.lng, point.lat]
          },
          properties: {}
        }
      });

      map.addLayer({
        id: snapId,
        type: 'circle',
        source: snapSourceId,
        paint: {
          'circle-radius': 8,
          'circle-color': '#10b981', // green-500
          'circle-stroke-color': '#ffffff',
          'circle-stroke-width': 3,
          'circle-opacity': 0.8
        }
      });

      console.log(`✅ Snap marker successfully added to map`);

    } catch (error) {
      console.warn('Failed to add snap marker:', error.message);
    }
  }, [map]);

  // Remove snap marker
  const removeSnapMarker = useCallback(() => {
    if (!map) return;

    const snapId = 'measurement-snap-marker';
    const snapSourceId = `${snapId}-source`;

    try {
      if (map.getLayer(snapId)) map.removeLayer(snapId);
      if (map.getSource(snapSourceId)) map.removeSource(snapSourceId);
      console.log(`🗑️ Snap marker removed`);
    } catch (error) {
      console.debug('Error removing snap marker:', error.message);
    }
  }, [map]);

  // Handle map click events
  const handleMapClick = useCallback(async (e: maplibregl.MapMouseEvent) => {
    const { mode, snappingEnabled } = measurementState;

    // Provide visual feedback for click registration
    if (map) {
      const originalCursor = map.getCanvas().style.cursor;
      map.getCanvas().style.cursor = 'progress'; // Show processing cursor briefly

      // Reset cursor after a short delay
      setTimeout(() => {
        if (map) {
          map.getCanvas().style.cursor = originalCursor;
        }
      }, 200);
    }

    if (mode === 'click-drag') {
      // Handle click-drag measurement
      console.log(`🖱️ CLICK-DRAG MODE: snapping=${snappingEnabled}, click at ${e.lngLat.lat.toFixed(6)}, ${e.lngLat.lng.toFixed(6)}`);
      const snappedPoint = await findNearestPLSSFeature(e.lngLat.lng, e.lngLat.lat, map, snappingEnabled, stateName);
      const newPoint = { ...snappedPoint };

      // Show snap feedback and marker if snapping was enabled and a feature was found
      if (snappingEnabled && snappedPoint.snappedFeature) {
        console.log(`🎯 CLICK-DRAG SNAP DETECTED: ${snappedPoint.snappedFeature} at ${snappedPoint.lat.toFixed(6)}, ${snappedPoint.lng.toFixed(6)}`);
        console.log('🚨 SETTING SNAP FEEDBACK...');
        setSnapFeedback({
          featureName: snappedPoint.snappedFeature,
          coordinates: { lng: snappedPoint.lng, lat: snappedPoint.lat },
          isVisible: true
        });
        drawSnapMarker(snappedPoint);
        console.log('✅ Snap feedback and marker set!');
      } else if (snappingEnabled) {
        console.log('⚠️ Click-drag: Snapping enabled but no feature found to snap to');
      } else {
        console.log('🔇 Snapping disabled for click-drag');
      }

      addMeasurementPoint(newPoint);

      // Check if we have enough points for a measurement
      const updatedPoints = [...measurementState.currentMeasurement, newPoint];
      if (updatedPoints.length === 2) {
        const distance = calculateDistance(updatedPoints[0], updatedPoints[1]);
        const bearing = calculateBearing(updatedPoints[0], updatedPoints[1]);

        const measurement: Measurement = {
          id: generateMeasurementId(),
          points: updatedPoints,
          distance,
          bearing,
          isVisible: true
        };

        addMeasurement(measurement);
        resetCurrentMeasurement();
        console.log(`📏 Created measurement: ${distance.toFixed(1)} ft at ${bearing?.toFixed(1)}°`);
      }
    } else if (mode === 'direct-input') {
      // Handle direct input start point selection
      console.log(`📍 DIRECT-INPUT MODE: snapping=${snappingEnabled}, click at ${e.lngLat.lat.toFixed(6)}, ${e.lngLat.lng.toFixed(6)}`);
      const snappedPoint = await findNearestPLSSFeature(e.lngLat.lng, e.lngLat.lat, map, snappingEnabled, stateName);
      setDirectStartPoint(snappedPoint);

      // Show snap feedback and marker if snapping was enabled and a feature was found
      if (snappingEnabled && snappedPoint.snappedFeature) {
        console.log(`🎯 DIRECT-INPUT SNAP DETECTED: ${snappedPoint.snappedFeature} at ${snappedPoint.lat.toFixed(6)}, ${snappedPoint.lng.toFixed(6)}`);
        console.log('🚨 SETTING SNAP FEEDBACK FOR DIRECT-INPUT...');
        setSnapFeedback({
          featureName: snappedPoint.snappedFeature,
          coordinates: { lng: snappedPoint.lng, lat: snappedPoint.lat },
          isVisible: true
        });
        drawSnapMarker(snappedPoint);
        console.log('✅ Direct-input snap feedback and marker set!');
      } else if (snappingEnabled) {
        console.log('⚠️ Direct-input: Snapping enabled but no feature found to snap to');
      } else {
        console.log('🔇 Snapping disabled for direct-input');
      }

      console.log(`📍 Set measurement start point: ${snappedPoint.lat.toFixed(6)}, ${snappedPoint.lng.toFixed(6)}`);
    }
  }, [map, measurementState, addMeasurementPoint, addMeasurement, resetCurrentMeasurement, setDirectStartPoint, setSnapFeedback, drawSnapMarker, stateName]);

  // Handle direct measurement creation
  const handleCreateDirectMeasurement = useCallback(() => {
    const { directStartPoint, directDistance, selectedDirection, directBearing } = measurementState;

    if (!directStartPoint || !directDistance) return;

    const distance = parseFloat(directDistance);

    if (isNaN(distance)) {
      console.warn('❌ Invalid distance value');
      return;
    }

    // Use custom bearing if provided, otherwise use selected direction
    let bearing: number;
    if (directBearing && directBearing.trim() !== '') {
      bearing = parseFloat(directBearing);
      if (isNaN(bearing)) {
        console.warn('❌ Invalid bearing value');
        return;
      }
    } else {
      bearing = directionToBearing(selectedDirection);
    }

    const endPoint = calculateEndPoint(directStartPoint, distance, bearing);

    const measurement: Measurement = {
      id: generateMeasurementId(),
      points: [directStartPoint, endPoint],
      distance,
      bearing,
      isVisible: true
    };

    addMeasurement(measurement);
    setDirectStartPoint(null);
    setDirectDistance('');
    setDirectBearing('');
    removeSnapMarker(); // Remove snap marker after measurement creation

    console.log(`📏 Created direct measurement: ${distance.toFixed(1)} ft at ${bearing.toFixed(1)}°`);
  }, [measurementState, addMeasurement, setDirectStartPoint, setDirectDistance, setDirectBearing, directionToBearing, removeSnapMarker]);



  // Handle measurement visibility toggle
  const handleToggleMeasurementVisibility = useCallback((measurementId: string) => {
    toggleMeasurementVisibility(measurementId);
  }, [toggleMeasurementVisibility]);

  // Handle measurement removal
  const handleRemoveMeasurement = useCallback((measurementId: string) => {
    removeMeasurement(measurementId);
  }, [removeMeasurement]);

  // Handle clearing all measurements
  const handleClearAllMeasurements = useCallback(() => {
    clearAllMeasurements();
    removeSnapMarker(); // Also remove any snap markers
  }, [clearAllMeasurements, removeSnapMarker]);

  // Update map cursor based on measurement mode and snapping state
  useEffect(() => {
    if (!map || !isLoaded) return;

    const { mode, snappingEnabled } = measurementState;

    // Show crosshair when snapping is enabled, otherwise use mode-specific cursor
    if (snappingEnabled) {
      map.getCanvas().style.cursor = 'crosshair';
    } else if (mode === 'click-drag') {
      map.getCanvas().style.cursor = 'crosshair';
    } else if (mode === 'direct-input') {
      map.getCanvas().style.cursor = 'pointer';
    } else {
      map.getCanvas().style.cursor = '';
    }

    return () => {
      if (map) {
        map.getCanvas().style.cursor = '';
      }
    };
  }, [map, isLoaded, measurementState.mode, measurementState.snappingEnabled]);

  // Manage snap marker lifecycle based on measurement state
  useEffect(() => {
    if (!map || !isLoaded) return;

    const { mode, measurements } = measurementState;

    // Remove snap marker when measurement mode is disabled or all measurements are cleared
    if (mode === 'disabled' || measurements.length === 0) {
      removeSnapMarker();
    }
  }, [map, isLoaded, measurementState.mode, measurementState.measurements.length, removeSnapMarker]);

  // Map event listeners
  useEffect(() => {
    if (!map || !isLoaded) return;

    const { mode } = measurementState;

    if (mode !== 'disabled') {
      map.on('click', handleMapClick);
    }

    return () => {
      map.off('click', handleMapClick);
    };
  }, [map, isLoaded, measurementState.mode, handleMapClick]);

  return (
    <div className={`measurement-manager ${className}`}>
      {/* Controls */}
      <MeasurementControls
        measurementState={measurementState}
        onModeChange={setMode}
        onToggleSnapping={toggleSnapping}
        onDirectDistanceChange={setDirectDistance}
        onDirectBearingChange={setDirectBearing}
        onSelectedDirectionChange={setSelectedDirection}
        onCreateDirectMeasurement={handleCreateDirectMeasurement}
        onToggleMeasurementVisibility={handleToggleMeasurementVisibility}
        onRemoveMeasurement={handleRemoveMeasurement}
        onClearAllMeasurements={handleClearAllMeasurements}
        onHideSnapFeedback={hideSnapFeedback}
      />

      {/* Overlay Manager */}
      <MeasurementOverlay
        measurements={measurementState.measurements}
        onMeasurementLoad={(measurement) => {
          console.log(`✅ Measurement loaded: ${measurement.id}`);
        }}
        onMeasurementUnload={(measurement) => {
          console.log(`🗑️ Measurement unloaded: ${measurement.id}`);
        }}
      />
    </div>
  );
};

export default MeasurementManager;
