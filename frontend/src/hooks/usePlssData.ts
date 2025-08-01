/**
 * PLSS Data Hook
 * Manages PLSS data fetching and state
 */
import { useState, useEffect, useCallback } from 'react';
import { mappingApi, PLSSDescription, PLSSResolveResponse } from '../services/mappingApi';

export interface PlssState {
  isLoading: boolean;
  error: string | null;
  availableStates: string[];
  resolvedCoordinates: PLSSResolveResponse | null;
}

export interface UsePlssDataReturn {
  state: PlssState;
  resolveCoordinates: (plssDescription: PLSSDescription) => Promise<PLSSResolveResponse>;
  clearError: () => void;
  resetState: () => void;
}

export const usePlssData = (): UsePlssDataReturn => {
  const [state, setState] = useState<PlssState>({
    isLoading: false,
    error: null,
    availableStates: [],
    resolvedCoordinates: null
  });

  // Load available states on mount
  useEffect(() => {
    const loadAvailableStates = async () => {
      try {
        setState(prev => ({ ...prev, isLoading: true, error: null }));
        
        const response = await mappingApi.getPLSSStates();
        
        setState(prev => ({
          ...prev,
          isLoading: false,
          availableStates: response.available_states || []
        }));
      } catch (error) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error';
        setState(prev => ({
          ...prev,
          isLoading: false,
          error: `Failed to load available states: ${errorMessage}`
        }));
      }
    };

    loadAvailableStates();
  }, []);

  // Resolve PLSS coordinates
  const resolveCoordinates = useCallback(async (plssDescription: PLSSDescription): Promise<PLSSResolveResponse> => {
    try {
      setState(prev => ({ ...prev, isLoading: true, error: null }));

      const response = await mappingApi.resolvePLSSCoordinates({
        plss_description: plssDescription
      });

      if (response.success) {
        setState(prev => ({
          ...prev,
          isLoading: false,
          resolvedCoordinates: response
        }));
      } else {
        setState(prev => ({
          ...prev,
          isLoading: false,
          error: response.error || 'Failed to resolve PLSS coordinates'
        }));
      }

      return response;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      const errorResponse: PLSSResolveResponse = {
        success: false,
        error: errorMessage
      };

      setState(prev => ({
        ...prev,
        isLoading: false,
        error: `PLSS resolution error: ${errorMessage}`
      }));

      return errorResponse;
    }
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setState(prev => ({ ...prev, error: null }));
  }, []);

  // Reset state
  const resetState = useCallback(() => {
    setState(prev => ({
      ...prev,
      error: null,
      resolvedCoordinates: null
    }));
  }, []);

  return {
    state,
    resolveCoordinates,
    clearError,
    resetState
  };
};