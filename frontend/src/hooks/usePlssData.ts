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

  // Extract polling logic into a reusable function
  const pollDownloadProgress = async (plssState: string) => {
    while (true) {
      const p = await plssDataService.getDownloadProgress(plssState);
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
      } else if (stage === 'building:index' || stage === 'writing:manifest') {
        // Final phase - no percentage, just completion message
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: 'Finishing up...',
          parquetPhase: true,
          parquetStatus: (p as any).status || 'Finalizing installation...',
          estimatedTime: 'Almost done',
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

    // FIXED: Verify data is actually available before marking as ready
    console.log('🏁 Download complete, verifying data availability...');
    const finalCheck = await plssDataService.checkDataStatus(plssState);
    if (finalCheck.available) {
      setState(prev => ({ 
        ...prev, 
        status: 'ready', 
        progress: null, 
        mappingEnabled: true, 
        parquetPhase: false, 
        parquetStatus: null, 
        estimatedTime: null 
      }));
      console.log('✅ Data verification successful - download complete and ready!');
    } else {
      setState(prev => ({ 
        ...prev, 
        status: 'error', 
        error: 'Download completed but data verification failed. Please try again.', 
        progress: null, 
        parquetPhase: false, 
        parquetStatus: null, 
        estimatedTime: null 
      }));
      console.error('❌ Data verification failed after download completion');
    }
  };

  useEffect(() => {
    const initializeData = async () => {
      if (!schemaData) return;

      // Begin a new check cycle, but do NOT blindly reset modalDismissed here.
      // The dismissal should persist for the current state unless the state changes.
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

      // If the state has changed (e.g., new schema in a different state),
      // reset modalDismissed so the user is prompted again for the new state.
      setState(prev => ({
        ...prev,
        state: plssState,
        modalDismissed: prev.state !== plssState ? false : prev.modalDismissed,
      }));

      // FIXED: Check for active download and start polling if found
      const downloadStatus = await plssDataService.checkDownloadActive(plssState);
      if (downloadStatus.active) {
        setState(prev => ({ 
          ...prev, 
          status: 'downloading',
          progress: `${downloadStatus.stage || 'processing'}...`,
          mappingEnabled: false // Explicitly disable mapping
        }));
        
        // FIXED: Start polling for progress updates
        console.log('🔄 Active download detected, starting progress polling...');
        pollDownloadProgress(plssState);
        return;
      }

      // Only check data availability if download is not active
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
        mappingEnabled: statusResult.available ? true : false
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

    // Use the extracted polling function
    await pollDownloadProgress(state.state);
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