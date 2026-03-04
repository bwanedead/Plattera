import { useState, useCallback, useEffect } from 'react';
import { ProcessingResult, EnhancementSettings, RedundancySettings, ConsensusSettings } from '../types/imageProcessing';
import { fetchModelsAPI, processFilesAPI } from '../services/imageProcessingApi';
import { listTranscriptEditRuns } from '../services/transcriptEditAgentApi';

interface UseImageProcessingOptions {
  onProcessingComplete?: () => void;
  selectedDossierId?: string | null;
  /**
   * Optional callback fired when the backend auto-creates a dossier
   * (i.e. when no dossier id was supplied and initRun returns a new id).
   * This lets the caller keep its own dossier selection in sync.
   */
  onAutoCreatedDossierId?: (dossierId: string) => void;
}

export const useImageProcessing = (options?: UseImageProcessingOptions) => {
  const {
    onProcessingComplete: externalOnProcessingComplete,
    selectedDossierId,
    onAutoCreatedDossierId
  } = options || {};
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [sessionResults, setSessionResults] = useState<ProcessingResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<ProcessingResult | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [availableExtractionModes, setAvailableExtractionModes] = useState<Record<string, {name: string, description: string}>>({});
  const [selectedModel, setSelectedModel] = useState('gpt-o4-mini');
  const [extractionMode, setExtractionMode] = useState('legal_document_json_relaxed');
  const [loadingModes, setLoadingModes] = useState(true);
  const [enhancementSettings, setEnhancementSettings] = useState<EnhancementSettings>({
    contrast: 2.0,
    sharpness: 2.0,
    brightness: 1.5,
    color: 1.0
  });
  const [redundancySettings, setRedundancySettings] = useState<RedundancySettings>({
    enabled: false,
    count: 1,
    consensusStrategy: 'highest_confidence'
  });
  // Single vs Batch processing toggle (UI preference)
  const [processingMode, setProcessingMode] = useState<'single' | 'batch'>('single');
  const [consensusSettings, setConsensusSettings] = useState<ConsensusSettings>({
    enabled: false,
    model: 'gpt-5-consensus'
  });
  // DOSSIER SUPPORT
  const [internalSelectedDossierId, setSelectedDossierId] = useState<string | null>(null);
  const [onProcessingComplete, setOnProcessingComplete] = useState<(() => void) | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

  // Queue UI state to persist after staging is cleared
  type QueueItem = { fileName: string; jobId?: string; status: 'queued' | 'processing' | 'done' | 'error' };
  const [processingQueue, setProcessingQueue] = useState<QueueItem[]>([]);
  const [latestTranscriptEditRunId, setLatestTranscriptEditRunId] = useState<string | null>(null);

  const deriveTranscriptEditRunIdHint = useCallback((dossierId: string, transcriptionId: string): string => {
    const sec = Math.floor(Date.now() / 1000);
    const key = `${dossierId}${transcriptionId}`;
    let hash = 0x811c9dc5;
    for (let i = 0; i < key.length; i += 1) {
      hash ^= key.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193);
      hash >>>= 0;
    }
    const suffix = hash.toString(16).padStart(8, '0').slice(0, 8);
    return `tx_post_t0_${sec}_${suffix}`;
  }, []);

  const resolveTranscriptEditRunId = useCallback((result: ProcessingResult | null | undefined): string | null => {
    const metadata = (result?.result as any)?.metadata;
    const runId = typeof metadata?.transcript_edit_agent_run_id === 'string'
      ? metadata.transcript_edit_agent_run_id.trim()
      : '';
    return runId || null;
  }, []);

  // Dynamic redundancy defaults based on extraction mode
  const getRedundancyDefaults = (mode: string): RedundancySettings => {
    if (mode === 'legal_document_json' || mode === 'legal_document_json_relaxed') {
      return {
        enabled: true,
        count: 3,
        consensusStrategy: 'sequential'
      };
    } else {
      return {
        enabled: false,
        count: 3,
        consensusStrategy: 'sequential'
      };
    }
  };

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setStagedFiles(prev => [...prev, ...acceptedFiles]);
  }, []);

  const removeStagedFile = (fileName: string) => {
    setStagedFiles(prev => prev.filter(f => f.name !== fileName));
  };

  // Auto-switch processing mode based on number of staged files
  useEffect(() => {
    try {
      if (stagedFiles.length > 1) {
        if (processingMode !== 'batch') setProcessingMode('batch');
      } else {
        if (processingMode !== 'single') setProcessingMode('single');
      }
    } catch {}
  }, [stagedFiles.length, processingMode]);

  const attachTranscriptEditRunFromResult = useCallback((result: ProcessingResult | null | undefined) => {
    const runId = resolveTranscriptEditRunId(result);
    if (runId) {
      setLatestTranscriptEditRunId(runId);
    }
  }, [resolveTranscriptEditRunId]);

  const attachLatestPostT0RunForResult = useCallback(async (result: ProcessingResult | null | undefined) => {
    const metadata = (result?.result as any)?.metadata || {};
    const dossierId = typeof metadata?.dossier_id === 'string' ? metadata.dossier_id.trim() : '';
    const transcriptionId = typeof metadata?.transcription_id === 'string' ? metadata.transcription_id.trim() : '';
    if (!dossierId || !transcriptionId) return;
    try {
      for (let attempt = 0; attempt < 12; attempt += 1) {
        const runs = await listTranscriptEditRuns(120);
        const candidates = runs.filter((run) => {
          const request = run?.request || {};
          return request?.dossier_id === dossierId && request?.transcription_id === transcriptionId && request?.trigger === 'post_t0';
        });
        const match = candidates.find((run) => run?.status === 'running') || candidates[0];
        const runId = typeof match?.run_id === 'string' ? match.run_id.trim() : '';
        if (runId) {
          setLatestTranscriptEditRunId(runId);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (error) {
      console.warn('Failed to resolve transcript edit run from registry:', error);
    }
  }, []);

  const handleProcess = async (userInstruction?: string, opts?: { runEditLoop?: boolean }) => {
    if (stagedFiles.length === 0) return;
    const runEditLoop = Boolean(opts?.runEditLoop);

    setIsProcessing(true);

    try {
      // Reduce noisy logs

      // Determine which dossier (if any) this run should attach to.
      // Precedence:
      // 1. Explicit null from caller => auto-create (no dossier id).
      // 2. Explicit string from caller => attach to that dossier.
      // 3. Undefined from caller => fall back to internal state (other contexts).
      let dossierIdToSend: string | undefined;
      if (selectedDossierId === null) {
        dossierIdToSend = undefined;
      } else if (typeof selectedDossierId === 'string' && selectedDossierId.length > 0) {
        dossierIdToSend = selectedDossierId;
      } else {
        dossierIdToSend = internalSelectedDossierId || undefined;
      }
      // If batch with auto-create (no dossier selected), DO NOT pre-create a dossier.
      const isAutoCreateBatch = processingMode === 'batch' && !dossierIdToSend;

      // Initialize run skeleton only when targeting an existing dossier or in single mode
      const firstFile = stagedFiles[0];
      let initTranscriptionId: string | undefined;
      let initDossierId: string | undefined;
      let transcriptEditRunIdHint: string | undefined;

      if (!isAutoCreateBatch) {
        try {
          const { dossierApi } = await import('../services/dossier/dossierApi');
          // Ensure backend is reachable before first init-run to avoid long cold-start hangs
          try {
            let ok = await dossierApi.health(800);
            if (!ok) {
              await new Promise(r => setTimeout(r, 1200));
              ok = await dossierApi.health(800);
            }
          } catch {}
          const initResult = await dossierApi.initRun({
            dossierId: dossierIdToSend || undefined,
            fileName: firstFile?.name,
            model: selectedModel,
            extractionMode: extractionMode,
            redundancyCount: redundancySettings.enabled ? redundancySettings.count : 1,
            autoLlmConsensus: consensusSettings.enabled,
            llmConsensusModel: consensusSettings.model,
            consensusStrategy: redundancySettings.consensusStrategy
          });

          if (initResult.success) {
            if (!dossierIdToSend && initResult.dossier_id) {
              setSelectedDossierId(initResult.dossier_id);
              try {
                onAutoCreatedDossierId?.(initResult.dossier_id);
              } catch {
                // Swallow to avoid breaking processing on UI callback issues.
              }
            }
            initTranscriptionId = initResult.transcription_id;
            initDossierId = initResult.dossier_id;
            if (runEditLoop && initDossierId && initTranscriptionId) {
              transcriptEditRunIdHint = deriveTranscriptEditRunIdHint(String(initDossierId), String(initTranscriptionId));
              setLatestTranscriptEditRunId(transcriptEditRunIdHint);
            }
          }
        } catch (initError) {
          console.warn('⚠️ Failed to initialize run skeleton (non-critical):', initError);
        }
        dossierIdToSend = initDossierId || dossierIdToSend;
      }
      // Reduce noisy logs

      // Fire immediate refresh so skeleton appears
      document.dispatchEvent(new Event('dossiers:refresh'));

      // Enforce cap client-side in batch mode (server also enforces)
      const filesToProcess = processingMode === 'batch' ? stagedFiles.slice(0, 20) : [stagedFiles[0]];

      const results = await processFilesAPI(
        filesToProcess,
        selectedModel,
        extractionMode,
        enhancementSettings,
        redundancySettings,
        consensusSettings,
        dossierIdToSend,
        // Only attach to a specific segment when we are explicitly targeting
        // an existing dossier. In auto-create mode this must be undefined.
        dossierIdToSend ? (selectedSegmentId || undefined) : undefined,
        initTranscriptionId,
        userInstruction,
        transcriptEditRunIdHint
      );

      // Initialize queue from results (batch path returns job ids in metadata)
      try {
        if (filesToProcess.length > 1) {
          const q: QueueItem[] = filesToProcess.map((f, i) => ({
            fileName: f.name,
            jobId: (results[i]?.result as any)?.metadata?.job_id,
            status: i === 0 ? 'processing' : 'queued',
          }));
          setProcessingQueue(q);
        } else if (filesToProcess.length === 1) {
          setProcessingQueue([{ fileName: filesToProcess[0].name, status: 'processing' }]);
        }
      } catch {}

      setSessionResults(prev => [...results, ...prev]);

      // If queued jobs were created, poll their status and update results upon completion
      results.forEach((r) => {
        const jobId = (r?.result as any)?.metadata?.job_id;
        if (r.status === 'processing' && jobId) {
          const poll = async () => {
            let attempts = 0;
            const maxAttempts = 600; // ~5 minutes at 500ms interval
            while (attempts < maxAttempts) {
              try {
                const resp = await fetch(`http://localhost:8000/api/image-to-text/jobs/${jobId}`);
                const data = await resp.json();
                if (data && typeof data.status === 'string') {
                  if (data.status === 'SUCCEEDED') {
                    const snapshot = data.result || {};
                    const completed: any = {
                      input: r.input,
                      status: 'completed' as const,
                      result: {
                        extracted_text: snapshot.extracted_text,
                        metadata: snapshot.metadata || {},
                      },
                    };
                    setSessionResults(prev => {
                      const copy = [...prev];
                      const idx = copy.findIndex(x => (x?.result as any)?.metadata?.job_id === jobId);
                      if (idx >= 0) copy[idx] = completed;
                      else copy.unshift(completed);
                      return copy;
                    });
                    // Update queue: mark this job done and advance next queued to processing
                    setProcessingQueue(prev => {
                      const list: QueueItem[] = prev.map(item => item.jobId === jobId ? { ...item, status: 'done' as const } : item);
                      const hasProcessing = list.some(i => i.status === 'processing');
                      if (!hasProcessing) {
                        const idxNext = list.findIndex(i => i.status === 'queued');
                        if (idxNext >= 0) list[idxNext] = { ...list[idxNext], status: 'processing' as const };
                      }
                      return list;
                    });
                    // Select first successful if none selected
                    if (!selectedResult) {
                      setSelectedResult(completed);
                    }
                    if (runEditLoop) {
                      attachTranscriptEditRunFromResult(completed);
                    }
                    return;
                  }
                  if (data.status === 'FAILED' || data.status === 'CANCELED') {
                    const failed: any = { input: r.input, status: 'error' as const, result: null, error: data.error || 'Processing failed' };
                    setSessionResults(prev => {
                      const copy = [...prev];
                      const idx = copy.findIndex(x => (x?.result as any)?.metadata?.job_id === jobId);
                      if (idx >= 0) copy[idx] = failed;
                      else copy.unshift(failed);
                      return copy;
                    });
                    setProcessingQueue(prev => {
                      const list: QueueItem[] = prev.map(item => item.jobId === jobId ? { ...item, status: 'error' as const } : item);
                      const hasProcessing = list.some(i => i.status === 'processing');
                      if (!hasProcessing) {
                        const idxNext = list.findIndex(i => i.status === 'queued');
                        if (idxNext >= 0) list[idxNext] = { ...list[idxNext], status: 'processing' as const };
                      }
                      return list;
                    });
                    return;
                  }
                }
              } catch {
                // ignore and retry
              }
              await new Promise(r => setTimeout(r, 500));
              attempts += 1;
            }
          };
          // Fire and forget
          poll();
        }
      });

      const firstSuccessful = results.find(r => r.status === 'completed') || results[0];
      if (firstSuccessful) {
        setSelectedResult(firstSuccessful);
        attachTranscriptEditRunFromResult(firstSuccessful);
        if (!resolveTranscriptEditRunId(firstSuccessful)) {
          void attachLatestPostT0RunForResult(firstSuccessful);
        }
        if (runEditLoop && firstSuccessful.status === 'completed') {
          const runId = resolveTranscriptEditRunId(firstSuccessful);
          if (!runId) {
            void attachLatestPostT0RunForResult(firstSuccessful);
          }
        }
      }

      setStagedFiles([]);

      // Notify dossier manager of new processing completion
      if (onProcessingComplete) {
        onProcessingComplete();
      }
      if (externalOnProcessingComplete) {
        externalOnProcessingComplete();
      }

      return firstSuccessful;
    } catch (error) {
      console.error('Error processing files:', error);
      throw error;
    } finally {
      setIsProcessing(false);
      // If all queue items are done or error, keep the list visible until user adds new files
    }
  };

  const selectResult = (result: ProcessingResult) => {
    setSelectedResult(result);
  };

  // Load models and extraction modes on mount
  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
    
    const loadExtractionModes = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/process/types')
        const data = await response.json()
        
        if (data.status === 'success' && data.processing_types?.['image-to-text']?.extraction_modes) {
          setAvailableExtractionModes(data.processing_types['image-to-text'].extraction_modes)
        } else {
          throw new Error(data.error || 'Invalid response format')
        }
      } catch (error) {
        console.warn('Failed to load extraction modes from API, using defaults:', error)
        setAvailableExtractionModes({
          'legal_document_json_relaxed': { name: 'Legal Document JSON (Relaxed)', description: 'Structured JSON + local validation/repair' },
          'generic_document_json': { name: 'Generic Document JSON', description: 'Verbatim mainText + sideTexts' }
        })
      } finally {
        setLoadingModes(false)
      }
    }
    
    loadExtractionModes();
  }, []);

  // Update redundancy settings when extraction mode changes
  useEffect(() => {
    const newDefaults = getRedundancyDefaults(extractionMode);
    setRedundancySettings(newDefaults);
  }, [extractionMode]);

  // Periodic reconciliation while there are active/queued jobs
  useEffect(() => {
    const hasActive = processingQueue.some(q => q.status === 'queued' || q.status === 'processing');
    if (!hasActive) return;

    let cancelled = false;
    const interval = setInterval(async () => {
      if (cancelled) return;
      try {
        const resp = await fetch('http://localhost:8000/api/image-to-text/jobs');
        if (!resp.ok) return;
        const payload = await resp.json();
        const jobs = (payload?.jobs || []) as Array<{ id: string; status: string; result?: any; error?: string }>;
        const statusById = new Map(jobs.map(j => [j.id, j]));

        let anyCompleted = false;
        setProcessingQueue(prev => {
          const list: QueueItem[] = prev.map(item => {
            if (!item.jobId) return item;
            const j = statusById.get(item.jobId);
            if (!j) return item;
            if (j.status === 'SUCCEEDED' && item.status !== 'done') {
              anyCompleted = true;
              return { ...item, status: 'done' as const };
            }
            if ((j.status === 'FAILED' || j.status === 'CANCELED') && item.status !== 'error') {
              return { ...item, status: 'error' as const };
            }
            return item;
          });

          const hasProcessing = list.some(i => i.status === 'processing');
          if (!hasProcessing) {
            const idxNext = list.findIndex(i => i.status === 'queued');
            if (idxNext >= 0) list[idxNext] = { ...list[idxNext], status: 'processing' as const };
          }
          return list;
        });

        if (anyCompleted) {
          document.dispatchEvent(new Event('dossiers:refresh'));
        }
      } catch {
        // ignore; next tick will retry
      }
    }, 3000);

    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [processingQueue]);

  useEffect(() => {
    const runId = resolveTranscriptEditRunId(selectedResult);
    if (runId) {
      setLatestTranscriptEditRunId(runId);
    }
  }, [selectedResult, resolveTranscriptEditRunId]);

  useEffect(() => {
    for (const result of sessionResults) {
      const runId = resolveTranscriptEditRunId(result);
      if (runId) {
        setLatestTranscriptEditRunId(runId);
        return;
      }
    }
  }, [sessionResults, resolveTranscriptEditRunId]);

  return {
    // State
    stagedFiles,
    sessionResults,
    selectedResult,
    isProcessing,
    availableModels,
    availableExtractionModes,
    selectedModel,
    extractionMode,
    loadingModes,
    enhancementSettings,
    redundancySettings,
    consensusSettings,
    processingMode,
    processingQueue,
    latestTranscriptEditRunId,
    // DOSSIER SUPPORT
    selectedDossierId,
    onProcessingComplete,
    selectedSegmentId,
    // Actions
    onDrop,
    removeStagedFile,
    handleProcess,
    selectResult,
    setSelectedModel,
    setExtractionMode,
    setEnhancementSettings,
    setRedundancySettings,
    setConsensusSettings,
    setSessionResults,
    setProcessingMode,
    // DOSSIER ACTIONS
    setSelectedDossierId,
    setOnProcessingComplete,
    setSelectedSegmentId,
  };
}; 
