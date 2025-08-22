/**
 * Container Overlay State Hook
 * Manages state for container-based PLSS overlays
 */

import { useState, useCallback } from 'react';
import { ContainerOverlayState } from '../components/mapping/overlays/ContainerOverlayManager';

export const useContainerOverlayState = (initialState?: Partial<ContainerOverlayState>) => {
  const [overlayState, setOverlayState] = useState<ContainerOverlayState>({
    showTownship: false,
    showRange: false,
    showGrid: false,
    showSections: false,
    showQuarterSections: false,
    showSubdivisions: false,
    ...initialState,
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
      showTownship: false,
      showRange: false,
      showGrid: false,
      showSections: false,
      showQuarterSections: false,
      showSubdivisions: false,
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


