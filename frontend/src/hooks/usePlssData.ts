/**
 * PLSS Data Hook - State management for PLSS data
 * Separates state logic from UI components
 */
import { useState, useEffect } from 'react';
import { plssDataService, PLSSDataState } from '../services/plss';
import { presentPlssProgress, PlssUiProgress } from '../services/plss/progressPresenter';

// Extend the state to include modal dismissal
interface ExtendedPLSSDataState extends PLSSDataState {
  modalDismissed: boolean;
  mappingEnabled: boolean;
  // Parquet finalization UI signals
  parquetPhase?: boolean;
  parquetStatus?: string | null;
  estimatedTime?: string | null;
  uiProgress?: PlssUiProgress;
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
    uiProgress: undefined,
  });

  // Extract polling logic into a reusable function
  const pollDownloadProgress = async (plssState: string) => {
    while (true) {
      const p = await plssDataService.getDownloadProgress(plssState);
      if (p.error) {
        console.error('🧭 [PLSS] progress poll error', {
          state: plssState,
          error: p.error,
        });
        setState(prev => ({ ...prev, status: 'error', error: p.error || null, progress: null }));
        return;
      }
      const stage = p.stage || 'working';
      const stageNorm = String(stage).toLowerCase();
      const overall = p.overall || { downloaded: 0, total: 0, percent: 0 };
      const ui = presentPlssProgress({
        stage: p.stage,
        overall: p.overall,
        status: (p as any).status,
        estimated_time: (p as any).estimated_time,
        final_phase: (p as any).final_phase,
      });
      
      // Detect parquet building phase for better UI; keep full stage
      // resolution (e.g. "building:parquet:townships").
      if (stageNorm.startsWith('building:parquet')) {
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: ui.headline,
          parquetPhase: true,
          parquetStatus: ui.detail || (p as any).status || 'Building parquet files...',
          estimatedTime: (p as any).estimated_time || '15-20 minutes',
          uiProgress: ui,
        }));
      } else if (stageNorm === 'building:index' || stageNorm === 'writing:manifest') {
        // Final phase - no percentage, just completion message
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: ui.headline || 'Finalizing PLSS data…',
          parquetPhase: true,
          parquetStatus: ui.detail || (p as any).status || 'Finalizing installation...',
          estimatedTime: (p as any).estimated_time || 'Almost done',
          uiProgress: ui,
        }));
      } else {
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: ui.headline || `${stage} ${overall.percent || 0}%`,
          parquetPhase: false,
          parquetStatus: null,
          estimatedTime: null,
          uiProgress: ui,
        }));
      }
      
      if (stageNorm === 'canceled') {
        console.error('🧭 [PLSS] download stage=canceled', { state: plssState });
        setState(prev => ({
          ...prev,
          status: 'canceled',
          error: 'Download was canceled',
          progress: null,
          parquetPhase: false,
          parquetStatus: null,
          estimatedTime: null,
          uiProgress: ui,
        }));
        return;
      }
      
      if (stageNorm === 'complete') {
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

      // 1) Check for active download; treat errors as "unknown", not "definitely idle".
      const downloadStatus = await plssDataService.checkDownloadActive(plssState);
      if (downloadStatus.active) {
        setState(prev => ({ 
          ...prev, 
          status: 'downloading',
          progress: `${downloadStatus.stage || 'processing'}...`,
          mappingEnabled: false
        }));
        console.log('🔄 Active PLSS download detected, resuming progress polling...', {
          state: plssState,
          stage: downloadStatus.stage,
        });
        await pollDownloadProgress(plssState);
        return;
      }

      // 2) Belt-and-suspenders: peek at progress once; if mid-flight, resume.
      const p = await plssDataService.getDownloadProgress(plssState);
      if (p.stage && !['idle', 'complete', 'canceled'].includes(p.stage)) {
        const overall = p.overall || { percent: 0 };
        setState(prev => ({
          ...prev,
          status: 'downloading',
          progress: `${p.stage} ${overall.percent || 0}%`,
          mappingEnabled: false,
        }));
        console.log('🔄 PLSS progress indicates in-flight download; resuming polling...', {
          state: plssState,
          stage: p.stage,
          percent: overall.percent || 0,
        });
        await pollDownloadProgress(plssState);
        return;
      }

      // 3) Only check data availability if download is not active. If we *think*
      // a download is idle but the previous state was actively downloading, keep
      // the downloading state and let the polling loop drive us to a terminal
      // result instead of snapping back to "missing" or "prompt".
      const statusResult = await plssDataService.checkDataStatus(plssState);
      if (statusResult.error) {
        setState(prev => ({ 
          ...prev, 
          status: 'error', 
          error: statusResult.error || null
        }));
        return;
      }

      // Set status based on availability, but avoid downgrading an active
      // download back to "missing" based on a single availability probe.
      setState(prev => {
        if (prev.status === 'downloading') {
          console.error('🧭 [PLSS] ignoring availability check while downloading', {
            state: plssState,
            statusResult,
          });
          return prev;
        }
        return {
          ...prev,
          status: statusResult.available ? 'ready' : 'missing',
          mappingEnabled: statusResult.available ? true : false,
        };
      });
    };

    initializeData();
  }, [schemaData]);

  // Download function for when user clicks download
  const downloadData = async () => {
    if (!state.state) return;

    // Prevent double-start while a download is already in progress
    if (state.status === 'downloading') {
      console.log('⬇️ PLSS download already in progress, ignoring duplicate request', {
        state: state.state,
        status: state.status,
        progress: state.progress,
      });
      return;
    }

    // Record last state for global monitors (best-effort only) and reset any
    // previous overlay dismissal so each new download session can surface the
    // progress overlay as the primary UI again.
    try {
      localStorage.setItem('plss:lastState', state.state);
      localStorage.removeItem(`plss:overlayDismissed:${state.state}`);
    } catch {
      // ignore storage errors – non-fatal
    }

    // Proactively signal that detailed progress can be shown. The overlay will
    // only render once the monitor observes an active download for this state,
    // but this keeps the contract explicit: a user‑initiated download is a
    // "reset moment" for overlay visibility.
    try {
      document.dispatchEvent(new Event('plss:open-modal'));
    } catch {
      // ignore environments where document is not available
    }

    setState(prev => ({ ...prev, status: 'downloading', progress: 'Starting...' }));

    // Start background download
    await plssDataService.startBackgroundDownload(state.state);

    // Use the extracted polling function
    await pollDownloadProgress(state.state);
  };

  // Cancel current download
  const cancelDownload = async () => {
    if (!state.state) return;
    // Optimistically mark as canceled so the UI and logs reflect user intent
    // immediately; the polling loop will observe stage="canceled" shortly
    // after the backend processes the request.
    setState(prev => ({
      ...prev,
      status: 'canceled',
      progress: null,
      parquetPhase: false,
      parquetStatus: null,
      estimatedTime: null,
    }));
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