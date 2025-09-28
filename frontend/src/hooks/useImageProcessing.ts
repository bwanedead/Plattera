import { useState, useCallback, useEffect } from 'react';
import { ProcessingResult, EnhancementSettings, RedundancySettings, ConsensusSettings } from '../types/imageProcessing';
import { fetchModelsAPI, processFilesAPI } from '../services/imageProcessingApi';

interface UseImageProcessingOptions {
  onProcessingComplete?: () => void;
  selectedDossierId?: string | null;
}

export const useImageProcessing = (options?: UseImageProcessingOptions) => {
  const { onProcessingComplete: externalOnProcessingComplete, selectedDossierId } = options || {};
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [sessionResults, setSessionResults] = useState<ProcessingResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<ProcessingResult | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [availableModels, setAvailableModels] = useState<Record<string, any>>({});
  const [availableExtractionModes, setAvailableExtractionModes] = useState<Record<string, {name: string, description: string}>>({});
  const [selectedModel, setSelectedModel] = useState('gpt-o4-mini');
  const [extractionMode, setExtractionMode] = useState('legal_document_json');
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
  const [processingMode, setProcessingMode] = useState<'single' | 'batch'>('batch');
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

  // Dynamic redundancy defaults based on extraction mode
  const getRedundancyDefaults = (mode: string): RedundancySettings => {
    if (mode === 'legal_document_json') {
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

  const handleProcess = async () => {
    if (stagedFiles.length === 0) return;

    setIsProcessing(true);

    try {
      // Reduce noisy logs

      // Prefer internal state; fall back to prop
      let dossierIdToSend: string | undefined = (internalSelectedDossierId || selectedDossierId) || undefined;
      // If batch with auto-create (no dossier selected), DO NOT pre-create a dossier.
      const isAutoCreateBatch = processingMode === 'batch' && !dossierIdToSend;

      // Initialize run skeleton only when targeting an existing dossier or in single mode
      const firstFile = stagedFiles[0];
      let initTranscriptionId: string | undefined;
      let initDossierId: string | undefined;

      if (!isAutoCreateBatch) {
        try {
          const { dossierApi } = await import('../services/dossier/dossierApi');
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
            }
            initTranscriptionId = initResult.transcription_id;
            initDossierId = initResult.dossier_id;
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
        selectedSegmentId || undefined,
        initTranscriptionId
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
                      const list = prev.map(item => item.jobId === jobId ? { ...item, status: 'done' } : item);
                      const hasProcessing = list.some(i => i.status === 'processing');
                      if (!hasProcessing) {
                        const idxNext = list.findIndex(i => i.status === 'queued');
                        if (idxNext >= 0) list[idxNext] = { ...list[idxNext], status: 'processing' };
                      }
                      return list;
                    });
                    // Select first successful if none selected
                    if (!selectedResult) {
                      setSelectedResult(completed);
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
                      const list = prev.map(item => item.jobId === jobId ? { ...item, status: 'error' } : item);
                      const hasProcessing = list.some(i => i.status === 'processing');
                      if (!hasProcessing) {
                        const idxNext = list.findIndex(i => i.status === 'queued');
                        if (idxNext >= 0) list[idxNext] = { ...list[idxNext], status: 'processing' };
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
          'legal_document_json': { name: 'Legal Document JSON', description: 'Structured JSON format' },
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
          const list = prev.map(item => {
            if (!item.jobId) return item;
            const j = statusById.get(item.jobId);
            if (!j) return item;
            if (j.status === 'SUCCEEDED' && item.status !== 'done') {
              anyCompleted = true;
              return { ...item, status: 'done' };
            }
            if ((j.status === 'FAILED' || j.status === 'CANCELED') && item.status !== 'error') {
              return { ...item, status: 'error' };
            }
            return item;
          });

          const hasProcessing = list.some(i => i.status === 'processing');
          if (!hasProcessing) {
            const idxNext = list.findIndex(i => i.status === 'queued');
            if (idxNext >= 0) list[idxNext] = { ...list[idxNext], status: 'processing' };
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