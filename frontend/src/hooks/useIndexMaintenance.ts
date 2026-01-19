import { useState, useEffect, useCallback, useRef } from 'react';
import { indexMaintenanceApi } from '../services/retrieval/indexMaintenanceService';
import { 
  DiagnoseResponse, 
  ExecuteIndexRequest, 
  IndexJob, 
  PoolIdentifier 
} from '../types/retrieval';

export function useIndexMaintenance() {
  // State
  const [pool, setPool] = useState<PoolIdentifier>('FINAL_SEGMENTS');
  const [diagnoseResult, setDiagnoseResult] = useState<DiagnoseResponse | null>(null);
  const [isLoadingDiagnose, setIsLoadingDiagnose] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Execution & Jobs
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<IndexJob | null>(null);
  const [isExecuting, setIsExecuting] = useState(false); // Creating the job

  // UI State
  const [detailsOpen, setDetailsOpen] = useState(false);
  
  // Polling Refs
  const jobPollTimeoutRef = useRef<number | null>(null);
  const diagnosePollTimeoutRef = useRef<number | null>(null);

  // ============================================================================
  // DIAGNOSE
  // ============================================================================

  const fetchDiagnose = useCallback(async (includeSlicesOverride?: boolean) => {
    setIsLoadingDiagnose(true);
    setError(null);
    try {
      const includeSlices = includeSlicesOverride ?? detailsOpen;
      const res = await indexMaintenanceApi.diagnoseIndex(pool, includeSlices);
      setDiagnoseResult(res);
    } catch (err: any) {
      console.error('Diagnose failed:', err);
      setError(err.message || 'Failed to diagnose index');
    } finally {
      setIsLoadingDiagnose(false);
    }
  }, [pool, detailsOpen]);

  // Initial load + pool change
  useEffect(() => {
    fetchDiagnose();
  }, [fetchDiagnose]);

  // Fetch slices when details open
  useEffect(() => {
    if (detailsOpen && diagnoseResult && !diagnoseResult.slice_diagnoses) {
      fetchDiagnose(true);
    }
  }, [detailsOpen, diagnoseResult, fetchDiagnose]);

  // ============================================================================
  // EXECUTION
  // ============================================================================

  const executeIndex = async (req: Omit<ExecuteIndexRequest, 'pool_identifier'>) => {
    setIsExecuting(true);
    try {
      const res = await indexMaintenanceApi.executeIndex({
        ...req,
        pool_identifier: pool
      });
      setActiveJobId(res.job_id);
      setActiveJob(null); // Reset current job view
      // Start polling immediately
      pollJob(res.job_id);
    } catch (err: any) {
      console.error('Execute failed:', err);
      setError(err.message || 'Failed to start indexing job');
    } finally {
      setIsExecuting(false);
    }
  };

  // ============================================================================
  // JOB POLLING
  // ============================================================================

  const pollJob = useCallback(async (jobId: string) => {
    try {
      const job = await indexMaintenanceApi.getIndexJob(jobId);
      setActiveJob(job);

      if (['queued', 'running'].includes(job.status)) {
        // Continue polling
        jobPollTimeoutRef.current = window.setTimeout(() => pollJob(jobId), 1000);
        
        // Optionally refresh diagnose periodically while running (every ~5s)
        // For simplicity v0, we won't strictly enforce a 5s diagnose poll unless requested,
        // but the brief says "optionally re-diagnose every 3-5s". 
        // Let's stick to simple post-job refresh for now to avoid race conditions.
      } else {
        // Terminal state
        // Refresh diagnose to show new counts
        fetchDiagnose();
      }
    } catch (err) {
      console.error('Job poll failed:', err);
      // Stop polling on 404/error? Or retry?
      // For now, retry slower
      jobPollTimeoutRef.current = window.setTimeout(() => pollJob(jobId), 3000);
    }
  }, [fetchDiagnose]);

  // Cleanup timers
  useEffect(() => {
    return () => {
      if (jobPollTimeoutRef.current) window.clearTimeout(jobPollTimeoutRef.current);
      if (diagnosePollTimeoutRef.current) window.clearTimeout(diagnosePollTimeoutRef.current);
    };
  }, []);

  return {
    pool,
    setPool,
    diagnoseResult,
    isLoadingDiagnose,
    error,
    activeJob,
    isExecuting,
    executeIndex,
    detailsOpen,
    setDetailsOpen,
    refreshDiagnose: () => fetchDiagnose()
  };
}
