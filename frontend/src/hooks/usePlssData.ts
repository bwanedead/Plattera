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

      // Use the new schema-based extraction
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

      const statusResult = await plssDataService.checkDataStatus(plssState);
      if (statusResult.error) {
        setState(prev => ({ 
          ...prev, 
          status: 'error', 
          error: statusResult.error || 'Unknown error' // Fix: ensure error is string | null
        }));
        return;
      }

      setState(prev => ({ 
        ...prev, 
        status: statusResult.available ? 'ready' : 'missing' 
      }));
    };

    initializeData();
  }, [schemaData]);

  const downloadData = async () => {
    if (!state.state) return;

    setState(prev => ({ 
      ...prev, 
      status: 'downloading', 
      progress: 'Downloading PLSS data...' 
    }));

    const result = await plssDataService.ensureData(state.state);
    
    if (result.success) {
      setState(prev => ({ 
        ...prev, 
        status: 'ready', 
        progress: null 
      }));
    } else {
      setState(prev => ({ 
        ...prev, 
        status: 'error', 
        error: result.error || 'Download failed',
        progress: null 
      }));
    }
  };

  return {
    ...state,
    downloadData,
  };
}