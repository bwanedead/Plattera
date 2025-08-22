/**
 * Container Overlay State Hook
 * Manages state for container-based PLSS overlays
 */

import { useState, useCallback } from 'react';

export interface ContainerOverlayState {
  showGrid: boolean;
  showTownship: boolean;
  showRange: boolean;
  showSections: boolean;
  showQuarterSections: boolean;
  showSubdivisions: boolean;
  // Label visibility states
  showGridLabels: boolean;
  showTownshipLabels: boolean;
  showRangeLabels: boolean;
  showSectionLabels: boolean;
  showQuarterSectionLabels: boolean;
  showSubdivisionLabels: boolean;
}

export const useContainerOverlayState = () => {
  const [overlayState, setOverlayState] = useState<ContainerOverlayState>({
    showGrid: false,
    showTownship: false,
    showRange: false,
    showSections: false,
    showQuarterSections: false,
    showSubdivisions: false,
    // Label visibility states
    showGridLabels: false,
    showTownshipLabels: false,
    showRangeLabels: false,
    showSectionLabels: false,
    showQuarterSectionLabels: false,
    showSubdivisionLabels: false,
  });

  const toggleOverlay = useCallback((key: keyof ContainerOverlayState) => {
    setOverlayState(prev => {
      const newState = { ...prev };
      newState[key] = !newState[key];
      
      // REMOVED: No automatic switching to grid when both township and range are on
      // Users can manually toggle grid if they want to see the cell
      
      return newState;
    });
  }, []);

  const setOverlay = useCallback((key: keyof ContainerOverlayState, value: boolean) => {
    setOverlayState(prev => {
      const newState = { ...prev };
      newState[key] = value;
      
      // No automatic switching - let each overlay be set independently
      
      return newState;
    });
  }, []);

  const resetOverlays = useCallback(() => {
    setOverlayState({
      showGrid: false,
      showTownship: false,
      showRange: false,
      showSections: false,
      showQuarterSections: false,
      showSubdivisions: false,
      // Reset label states
      showGridLabels: false,
      showTownshipLabels: false,
      showRangeLabels: false,
      showSectionLabels: false,
      showQuarterSectionLabels: false,
      showSubdivisionLabels: false,
    });
  }, []);

  const getActiveOverlays = useCallback(() => {
    return Object.entries(overlayState)
      .filter(([_, value]) => value)
      .map(([key, _]) => key);
  }, [overlayState]);

  return {
    overlayState,
    setOverlayState,
    toggleOverlay,
    setOverlay,
    resetOverlays,
    getActiveOverlays,
  };
};


