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
    ...initialState,
  });

  const toggleOverlay = useCallback((key: keyof ContainerOverlayState) => {
    setOverlayState(prev => {
      const newState = { ...prev };
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
      
      return newState;
    });
  }, []);

  const setOverlay = useCallback((key: keyof ContainerOverlayState, value: boolean) => {
    setOverlayState(prev => {
      const newState = { ...prev };
      newState[key] = value;
      
      // Special logic for grid vs township/range
      if (key === 'showGrid' && value) {
        newState.showTownship = false;
        newState.showRange = false;
      } else if ((key === 'showTownship' || key === 'showRange') && value) {
        newState.showGrid = false;
      }
      
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


