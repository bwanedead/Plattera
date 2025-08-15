/**
 * PLSS Data Hook - State management for PLSS data
 * Separates state logic from UI components
 */
import { useState, useEffect } from 'react';
import { plssDataService, PLSSDataState } from '../services/plss';

// Extend the state to include modal dismissal
  interface ExtendedPLSSDataState extends PLSSDataState {
  modalDismissed: boolean;
  mappingEnabled: boolean;
  // Parquet finalization UI signals
  parquetPhase?: boolean;
  parquetStatus?: string | null;
  estimatedTime?: string | null;
 }

export function usePLSSData(schemaData: any) {
  const [state, setState] = useState<ExtendedPLSSDataState>({
    status: 'unknown',
    state: null,
    error: null,
    progress: null,
    modalDismissed: false, // Add dismissal tracking
    mappingEnabled: false,
    parquetPhase: false,
    parquetStatus: null,
    estimatedTime: null,
  });

  useEffect(() => {
    const initializeData = async () => {
      if (!schemaData) return;

      setState(prev => ({ ...prev, status: 'checking', modalDismissed: false }));

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
          error: statusResult.error || null
        }));
        return;
      }

      // Set status based on availability
      setState(prev => ({ 
        ...prev, 
        status: statusResult.available ? 'ready' : 'missing',
        mappingEnabled: statusResult.available ? true : prev.mappingEnabled
      }));
    };

    initializeData();
  }, [schemaData]);

  // Download function for when user clicks download
  const downloadData = async () => {
    if (!state.state) return;

    setState(prev => ({ ...prev, status: 'downloading', progress: 'Starting...' }));

    // Start background download
    await plssDataService.startBackgroundDownload(state.state);

    // Poll progress until backend reports complete
    while (true) {
      const p = await plssDataService.getDownloadProgress(state.state);
      if (p.error) {
        setState(prev => ({ ...prev, status: 'error', error: p.error || null }));
        return;
      }
      const stage = p.stage || 'working';
      const overall = p.overall || { downloaded: 0, total: 0, percent: 0 };
      // Detect parquet building phase for better UI
      if (stage === 'building:parquet') {
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: `${stage} ${overall.percent || 0}%`,
          parquetPhase: true,
          parquetStatus: (p as any).status || 'Building parquet files...',
          estimatedTime: (p as any).estimated_time || '15-20 minutes',
        }));
      } else {
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: `${stage} ${overall.percent || 0}%`,
          parquetPhase: false,
          parquetStatus: null,
          estimatedTime: null,
        }));
      }
      if (stage === 'canceled') {
        setState(prev => ({ ...prev, status: 'missing', error: 'Download canceled', progress: null }));
        return;
      }
      if (stage === 'complete') {
        break;
      }
      await new Promise(r => setTimeout(r, 800));
    }

    setState(prev => ({ ...prev, status: 'ready', progress: null, mappingEnabled: true, parquetPhase: false, parquetStatus: null, estimatedTime: null }));
  };

  // Cancel current download
  const cancelDownload = async () => {
    if (!state.state) return;
    await plssDataService.cancelDownload(state.state);
  };

  // Function to dismiss the modal
  const dismissModal = () => {
    setState(prev => ({ ...prev, modalDismissed: true }));
  };

  // Explicit gate for enabling mapping after download completes
  const enableMapping = () => {
    setState(prev => ({ ...prev, mappingEnabled: true }));
  };
  const disableMapping = () => {
    setState(prev => ({ ...prev, mappingEnabled: false }));
  };

  return {
    ...state,
    downloadData,
    cancelDownload,
    dismissModal, // Expose dismiss function
    enableMapping,
    disableMapping,
  };
}