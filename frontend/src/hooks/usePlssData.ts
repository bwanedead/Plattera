/**
 * PLSS Data Hook - State management for PLSS data
 * Separates state logic from UI components
 */
import { useState, useEffect } from 'react';
import { plssDataService, PLSSDataState } from '../services/plssDataService';

export function usePLSSData(schemaData: any) {
  const [state, setState] = useState<PLSSDataState>({
    status: 'unknown',
    state: null,
    error: null,
    progress: null,
  });

  useEffect(() => {
    const initializeData = async () => {
      if (!schemaData) return;

      setState(prev => ({ ...prev, status: 'checking' }));

      // Extract state from schema
      const plssState = await plssDataService.extractStateFromSchema(schemaData);
      if (!plssState) {
        setState(prev => ({ 
          ...prev, 
          status: 'error', 
          error: 'Unable to determine state from schema data' 
        }));
        return;
      }

      setState(prev => ({ ...prev, state: plssState }));

      // Check if data exists locally (NO auto-download)
      const statusResult = await plssDataService.checkDataStatus(plssState);
      if (statusResult.error) {
        setState(prev => ({ 
          ...prev, 
          status: 'error', 
          error: statusResult.error
        }));
        return;
      }

      // Set status based on availability
      setState(prev => ({ 
        ...prev, 
        status: statusResult.available ? 'ready' : 'missing' 
      }));
    };

    initializeData();
  }, [schemaData]);

  // Download function for when user clicks download
  const downloadData = async () => {
    if (!state.state) return;

    setState(prev => ({ ...prev, status: 'downloading' }));

    const result = await plssDataService.downloadData(state.state);
    
    setState(prev => ({ 
      ...prev, 
      status: result.success ? 'ready' : 'error',
      error: result.error || null
    }));
  };

  return {
    ...state,
    downloadData, // Expose download function
  };
}