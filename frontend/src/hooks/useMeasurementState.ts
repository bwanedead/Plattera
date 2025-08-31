/**
 * Measurement State Hook
 * Manages state for measurement tools
 */

import { useState, useCallback } from 'react';
import { Measurement, MeasurementPoint } from '../utils/measurementUtils';

export type MeasurementMode = 'disabled' | 'click-drag' | 'direct-input';
export type CardinalDirection = 'N' | 'NE' | 'E' | 'SE' | 'S' | 'SW' | 'W' | 'NW';

export interface SnapFeedback {
  featureName: string;
  coordinates: { lng: number; lat: number };
  isVisible: boolean;
}

export interface MeasurementState {
  mode: MeasurementMode;
  snappingEnabled: boolean;
  measurements: Measurement[];
  currentMeasurement: MeasurementPoint[];
  directDistance: string;
  directBearing: string;
  selectedDirection: CardinalDirection;
  directStartPoint: MeasurementPoint | null;
  snapFeedback: SnapFeedback | null;
}

export const useMeasurementState = () => {
  const [measurementState, setMeasurementState] = useState<MeasurementState>({
    mode: 'disabled',
    snappingEnabled: false, // Start with snapping disabled for clarity
    measurements: [],
    currentMeasurement: [],
    directDistance: '',
    directBearing: '',
    selectedDirection: 'N',
    directStartPoint: null,
    snapFeedback: null,
  });

  const setMode = useCallback((mode: MeasurementMode) => {
    setMeasurementState(prev => ({
      ...prev,
      mode,
      currentMeasurement: [],
      directStartPoint: null,
      directDistance: '',
      directBearing: '',
      selectedDirection: 'N',
      snapFeedback: null,
    }));
  }, []);

  const toggleSnapping = useCallback(() => {
    setMeasurementState(prev => ({
      ...prev,
      snappingEnabled: !prev.snappingEnabled,
    }));
  }, []);

  const setDirectDistance = useCallback((distance: string) => {
    setMeasurementState(prev => ({
      ...prev,
      directDistance: distance,
    }));
  }, []);

  const setDirectBearing = useCallback((bearing: string) => {
    setMeasurementState(prev => ({
      ...prev,
      directBearing: bearing,
    }));
  }, []);

  const setDirectStartPoint = useCallback((point: MeasurementPoint | null) => {
    setMeasurementState(prev => ({
      ...prev,
      directStartPoint: point,
    }));
  }, []);

  const addMeasurementPoint = useCallback((point: MeasurementPoint) => {
    setMeasurementState(prev => ({
      ...prev,
      currentMeasurement: [...prev.currentMeasurement, point],
    }));
  }, []);

  const resetCurrentMeasurement = useCallback(() => {
    setMeasurementState(prev => ({
      ...prev,
      currentMeasurement: [],
    }));
  }, []);

  const addMeasurement = useCallback((measurement: Measurement) => {
    setMeasurementState(prev => ({
      ...prev,
      measurements: [...prev.measurements, measurement],
    }));
  }, []);

  const toggleMeasurementVisibility = useCallback((measurementId: string) => {
    setMeasurementState(prev => ({
      ...prev,
      measurements: prev.measurements.map(m =>
        m.id === measurementId ? { ...m, isVisible: !m.isVisible } : m
      ),
    }));
  }, []);

  const removeMeasurement = useCallback((measurementId: string) => {
    setMeasurementState(prev => ({
      ...prev,
      measurements: prev.measurements.filter(m => m.id !== measurementId),
    }));
  }, []);

  const clearAllMeasurements = useCallback(() => {
    setMeasurementState(prev => ({
      ...prev,
      measurements: [],
      currentMeasurement: [],
      directStartPoint: null,
      directDistance: '',
      directBearing: '',
      selectedDirection: 'N',
      snapFeedback: null,
    }));
  }, []);

  const setSelectedDirection = useCallback((direction: CardinalDirection) => {
    setMeasurementState(prev => ({
      ...prev,
      selectedDirection: direction,
    }));
  }, []);

  const setSnapFeedback = useCallback((feedback: SnapFeedback | null) => {
    setMeasurementState(prev => ({
      ...prev,
      snapFeedback: feedback,
    }));
  }, []);

  const hideSnapFeedback = useCallback(() => {
    setMeasurementState(prev => ({
      ...prev,
      snapFeedback: prev.snapFeedback ? { ...prev.snapFeedback, isVisible: false } : null,
    }));
  }, []);

  return {
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
  };
};
