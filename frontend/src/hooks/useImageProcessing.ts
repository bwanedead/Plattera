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
  const [consensusSettings, setConsensusSettings] = useState<ConsensusSettings>({
    enabled: false,
    model: 'gpt-5-consensus'
  });
  // DOSSIER SUPPORT
  const [internalSelectedDossierId, setSelectedDossierId] = useState<string | null>(null);
  const [onProcessingComplete, setOnProcessingComplete] = useState<(() => void) | null>(null);
  const [selectedSegmentId, setSelectedSegmentId] = useState<string | null>(null);

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

      // Prefer internal state updated by init-run; fall back to prop
      let dossierIdToSend: string | undefined = (internalSelectedDossierId || selectedDossierId) || undefined;
      // Reduce noisy logs

      // Initialize run skeleton before processing for immediate UI feedback
      const firstFile = stagedFiles[0];
      let initTranscriptionId: string | undefined;
      let initDossierId: string | undefined;

      try {
        const { dossierApi } = await import('../services/dossier/dossierApi');
        const initResult = await dossierApi.initRun({
          dossierId: selectedDossierId || undefined,
          fileName: firstFile?.name,
          model: selectedModel,
          extractionMode: extractionMode,
          redundancyCount: redundancySettings.enabled ? redundancySettings.count : 1,
          autoLlmConsensus: consensusSettings.enabled,
          llmConsensusModel: consensusSettings.model,
          consensusStrategy: redundancySettings.consensusStrategy
        });

        if (initResult.success) {
          // Update selected dossier ID if auto-created
          if (!selectedDossierId && initResult.dossier_id) {
            setSelectedDossierId(initResult.dossier_id);
          }
          initTranscriptionId = initResult.transcription_id;
          initDossierId = initResult.dossier_id;
          // Reduce noisy logs
        }
      } catch (initError) {
        console.warn('⚠️ Failed to initialize run skeleton (non-critical):', initError);
        // Continue with processing even if init fails
      }

      // Ensure we send the dossier created/returned by init-run to enable dossier endpoint + progressive saving
      dossierIdToSend = initDossierId || dossierIdToSend;
      // Reduce noisy logs

      // Fire immediate refresh so skeleton appears
      document.dispatchEvent(new Event('dossiers:refresh'));

      const results = await processFilesAPI(
        stagedFiles,
        selectedModel,
        extractionMode,
        enhancementSettings,
        redundancySettings,
        consensusSettings,
        dossierIdToSend,
        selectedSegmentId || undefined,
        initTranscriptionId
      );

      setSessionResults(prev => [...results, ...prev]);

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
          'legal_document_plain': { name: 'Legal Document Plain', description: 'Plain legal document transcription' },
          'legal_document_sectioned': { name: 'Legal Document Sectioned', description: 'With section markers' },
          'ultra_precise_legal': { name: 'Ultra Precise Legal', description: 'Maximum accuracy' },
          'legal_document_json': { name: 'Legal Document JSON', description: 'Structured JSON format' }
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
    // DOSSIER ACTIONS
    setSelectedDossierId,
    setOnProcessingComplete,
    setSelectedSegmentId,
  };
}; 