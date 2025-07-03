/*
🔴 CRITICAL REDUNDANCY IMPLEMENTATION DOCUMENTATION 🔴
=====================================================

THIS IS THE MAIN IMAGE PROCESSING UI COMPONENT - PRESERVE ALL WIRING BELOW 🔴

CURRENT WORKING STRUCTURE (DO NOT BREAK):
==========================================

1. STATE MANAGEMENT:
   - stagedFiles: File[] (files ready for processing)
   - sessionResults: any[] (processing history)
   - selectedResult: any (currently displayed result)
   - enhancementSettings: EnhancementSettings (image enhancement params)
   - CRITICAL: All existing state variables MUST remain unchanged

2. API INTEGRATION:
   - processFilesAPI() handles backend communication
   - fetchModelsAPI() loads available models
   - CRITICAL: API call structure MUST remain compatible
   - SAFE TO ADD: redundancy parameter to API calls

3. ENHANCEMENT SETTINGS:
   - EnhancementSettings interface defines image enhancement params
   - handleEnhancementChange() manages settings updates
   - CRITICAL: Enhancement flow MUST remain functional
   - SAFE TO ADD: redundancy settings alongside enhancement settings

4. UI COMPONENTS:
   - File dropzone for image uploads
   - Control panel with model/mode selection
   - Enhancement modal for image settings
   - Results viewer with text display
   - CRITICAL: All existing UI elements MUST remain functional

REDUNDANCY IMPLEMENTATION SAFETY RULES:
======================================

✅ SAFE TO ADD:
- RedundancySettings interface alongside EnhancementSettings
- redundancySettings state variable
- Redundancy controls in control panel
- Redundancy parameter to processFilesAPI()
- Redundancy display in results metadata

❌ DO NOT MODIFY:
- Existing state variable names or types
- EnhancementSettings interface structure
- processFilesAPI() core functionality
- handleProcess() core logic
- UI component structure
- File handling logic

CRITICAL API INTEGRATION POINTS:
===============================
- processFilesAPI() sends FormData to backend
- Backend expects specific field names (content_type, model, etc.)
- Response format must match ProcessingResult interface
- SAFE TO ADD: redundancy form field to FormData

CRITICAL UI INTEGRATION POINTS:
===============================
- Enhancement modal integration MUST remain functional
- File staging/processing flow MUST work unchanged
- Results display MUST show extracted_text correctly
- Error handling MUST work for failed processing

REDUNDANCY UI REQUIREMENTS:
==========================
1. Add redundancy controls to control panel (after enhancement section)
2. Include redundancy toggle and slider
3. Pass redundancy settings to processFilesAPI()
4. Display redundancy metadata in results (optional)
5. Maintain all existing functionality

TESTING CHECKPOINTS:
===================
After redundancy implementation, verify:
1. File upload and processing still works
2. Enhancement settings still function correctly
3. Results display correctly with redundancy enabled/disabled
4. All existing UI interactions remain functional
5. API communication works with new redundancy parameter
*/

import React, { useState, useCallback, useEffect } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ImageEnhancementModal } from './ImageEnhancementModal';
import { DraftLoader } from './DraftLoader';
import { 
  isJsonResult, 
  formatJsonAsText, 
  formatJsonPretty,
} from '../../utils/jsonFormatter';
import { saveDraft, getDraftCount, DraftSession } from '../../utils/draftStorage';
import { ControlPanel } from './ControlPanel';
import { ResultsViewer } from './ResultsViewer';
import { AnimatedBorder } from '../AnimatedBorder';

// Enhancement settings interface
interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

// Redundancy settings interface
interface RedundancySettings {
  enabled: boolean;
  count: number;
  consensusStrategy: string;
}

// --- Real API Calls (replacing the simulated ones) ---
const processFilesAPI = async (files: File[], model: string, mode: string, enhancementSettings: EnhancementSettings, redundancySettings: RedundancySettings) => {
  console.log(`Processing ${files.length} files with model: ${model} and mode: ${mode}`);
  
  const results = [];
  
  for (const file of files) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('content_type', 'image-to-text');
      formData.append('extraction_mode', mode);
      formData.append('model', model);
      formData.append('cleanup_after', 'true');
      
      // Add enhancement settings
      formData.append('contrast', enhancementSettings.contrast.toString());
      formData.append('sharpness', enhancementSettings.sharpness.toString());
      formData.append('brightness', enhancementSettings.brightness.toString());
      formData.append('color', enhancementSettings.color.toString());
      
      // Add redundancy setting
      formData.append('redundancy', redundancySettings.enabled ? redundancySettings.count.toString() : '1');
      
      // Consensus strategy (only relevant when redundancy is enabled)
      if (redundancySettings.enabled) {
        formData.append('consensus_strategy', redundancySettings.consensusStrategy);
      }

      const response = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      console.log("API response data:", data);

      if (data.status === 'success') {
        results.push({
          input: file.name,
          status: 'completed' as const,
          result: {
            extracted_text: data.extracted_text,
            metadata: {
              model_used: data.model_used,
              service_type: data.service_type,
              tokens_used: data.tokens_used,
              confidence_score: data.confidence_score,
              ...data.metadata
            }
          }
        });
      } else {
        results.push({
          input: file.name,
          status: 'error' as const,
          result: null,
          error: data.error || 'Processing failed'
        });
      }
    } catch (error) {
      results.push({
        input: file.name,
        status: 'error' as const,
        result: null,
        error: error instanceof Error ? error.message : 'Unknown error'
      });
    }
  }
  
  return results;
};

// Real API call for fetching models
const fetchModelsAPI = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/models');
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    if (data.status === 'success' && data.models) {
      return data.models;
    } else {
      throw new Error(data.error || 'Invalid response format');
    }
  } catch (error) {
    console.warn('Failed to load models from API, using defaults:', error);
    // Fallback to default models
    return {
      "gpt-4o": { name: "GPT-4o", provider: "openai" },
      "o3": { name: "o3", provider: "openai" },
      "gpt-4": { name: "GPT-4", provider: "openai" },
    };
  }
};

interface ProcessingResult {
  success: boolean;
  extracted_text: string;
  model_used: string;
  service_type: string;
  tokens_used?: number;
  confidence_score?: number;
  metadata?: any;
}

// Define the type for the component's props, including the onExit callback
interface ImageProcessingWorkspaceProps {
  onExit: () => void;
  onNavigateToTextSchema?: () => void;
}

// --- Main Component ---
export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ onExit, onNavigateToTextSchema }) => {
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [sessionResults, setSessionResults] = useState<any[]>([]);
  const [selectedResult, setSelectedResult] = useState<any>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isHistoryVisible, setIsHistoryVisible] = useState(true);
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
  const [showEnhancementModal, setShowEnhancementModal] = useState(false);
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>('best');
  const [selectedConsensusStrategy, setSelectedConsensusStrategy] = useState<string>('highest_confidence');
  
  // Navigation button hover states
  const [homeHovered, setHomeHovered] = useState(false);
  const [textSchemaHovered, setTextSchemaHovered] = useState(false);

  // Draft management state
  const [showDraftLoader, setShowDraftLoader] = useState(false);
  const [draftCount, setDraftCount] = useState(0);

  // Dynamic redundancy defaults based on extraction mode
  const getRedundancyDefaults = (mode: string): RedundancySettings => {
    if (mode === 'legal_document_json') {
      // JSON mode: Enable redundancy by default (semantic alignment is valuable)
      return {
        enabled: true,
        count: 3,
        consensusStrategy: 'highest_confidence'
      };
    } else {
      // Non-JSON mode: Disable redundancy by default (consensus not useful for plain text)
      return {
        enabled: false,
        count: 3,
        consensusStrategy: 'highest_confidence'
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
      const results = await processFilesAPI(
        stagedFiles, 
        selectedModel, 
        extractionMode, 
        enhancementSettings, 
        redundancySettings
      );
      
      // Add all results to session
      setSessionResults(prev => [...results, ...prev]);
      
      // Select the first successful result, or the first result if none succeeded
      const firstSuccessful = results.find(r => r.status === 'completed') || results[0];
      if (firstSuccessful) {
        setSelectedResult(firstSuccessful);
        setSelectedDraft('best'); // Reset to best draft for new results
      }
      
      setStagedFiles([]);
      setIsProcessing(false);
    } catch (error) {
      console.error('Error processing files:', error);
      setIsProcessing(false);
    }
  };

  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
    
    // Load extraction modes
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
        // Fallback to default modes
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

  const getCurrentText = useCallback(() => {
    if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
      return selectedResult?.error || 'No result available';
    }

    const redundancyAnalysis = selectedResult.result?.metadata?.redundancy_analysis;
    
    // Use selected consensus strategy if available
    if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
      const consensusText = redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
      // Format JSON as readable text if it's JSON
      return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
    }
    
    // Fallback to original logic
    if (!redundancyAnalysis) {
      const extractedText = selectedResult.result?.extracted_text || 'No text available';
      // Format JSON as readable text if it's JSON
      return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
    }

    // CRITICAL DRAFT SELECTION LOGIC
    if (selectedDraft === 'best') {
      const extractedText = selectedResult.result.extracted_text || '';
      // Format JSON as readable text if it's JSON
      return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
    } else if (selectedDraft === 'consensus') {
      const consensusText = redundancyAnalysis.consensus_text || selectedResult.result.extracted_text || '';
      // Format JSON as readable text if it's JSON
      return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
    } else if (typeof selectedDraft === 'number') {
      const individualResults = redundancyAnalysis.individual_results;
      const successfulResults = individualResults.filter((r: any) => r.success);
      if (selectedDraft < successfulResults.length) {
        const draftText = successfulResults[selectedDraft].text || '';
        // Format JSON as readable text if it's JSON
        return isJsonResult(draftText) ? formatJsonAsText(draftText) : draftText;
      }
    }

    // Fallback to main text
    const fallbackText = selectedResult.result.extracted_text || '';
    return isJsonResult(fallbackText) ? formatJsonAsText(fallbackText) : fallbackText;
  }, [selectedResult, selectedDraft, selectedConsensusStrategy]);

  // Get raw extracted text for JSON tab (without formatting)
  const getRawText = useCallback(() => {
    if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
      return selectedResult?.error || 'No result available';
    }

    const redundancyAnalysis = selectedResult.result?.metadata?.redundancy_analysis;
    
    // Use selected consensus strategy if available
    if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
      return redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
    }
    
    // Fallback to original logic
    if (!redundancyAnalysis) {
      return selectedResult.result?.extracted_text || 'No text available';
    }

    // Draft selection logic for raw text
    if (selectedDraft === 'best') {
      return selectedResult.result.extracted_text || '';
    } else if (selectedDraft === 'consensus') {
      return redundancyAnalysis.consensus_text || selectedResult.result.extracted_text || '';
    } else if (typeof selectedDraft === 'number') {
      const individualResults = redundancyAnalysis.individual_results;
      const successfulResults = individualResults.filter((r: any) => r.success);
      if (selectedDraft < successfulResults.length) {
        return successfulResults[selectedDraft].text || '';
      }
    }

    return selectedResult.result.extracted_text || '';
  }, [selectedResult, selectedDraft, selectedConsensusStrategy]);

  // Check if current result is JSON format
  const isCurrentResultJson = useCallback(() => {
    const rawText = getRawText();
    return isJsonResult(rawText);
  }, [getRawText]);

  // Initialize draft count on mount
  useEffect(() => {
    setDraftCount(getDraftCount());
  }, []);

  // Save draft functionality - only save the currently selected draft
  const handleSaveDraft = useCallback(() => {
    if (!selectedResult || selectedResult.status !== 'completed') {
      alert('No valid result to save');
      return;
    }

    try {
      const content = getRawText();
      
      // Get metadata only for the selected draft
      let draftMetadata = {};
      const redundancyAnalysis = selectedResult.result?.metadata?.redundancy_analysis;
      
      if (redundancyAnalysis && typeof selectedDraft === 'number') {
        // If it's a specific draft number, get metadata for that draft only
        const individualResults = redundancyAnalysis.individual_results;
        const successfulResults = individualResults?.filter((r: any) => r.success) || [];
        
        if (selectedDraft < successfulResults.length) {
          const specificDraft = successfulResults[selectedDraft];
          draftMetadata = {
            model_used: specificDraft.model || selectedResult.result?.metadata?.model_used || 'unknown',
            original_draft_index: selectedDraft,
            saved_draft_type: `draft_${selectedDraft + 1}`,
            confidence_score: specificDraft.confidence || 1.0,
            service_type: selectedResult.result?.metadata?.service_type || 'llm'
          };
        }
      } else {
        // For 'best' or 'consensus' drafts, use general metadata
        draftMetadata = {
          model_used: selectedResult.result?.metadata?.model_used || 'unknown',
          saved_draft_type: selectedDraft,
          confidence_score: selectedResult.result?.metadata?.confidence_score || 1.0,
          service_type: selectedResult.result?.metadata?.service_type || 'llm'
        } as any;
      }
      
      const savedDraft = saveDraft(content, (draftMetadata as any).model_used || 'unknown', draftMetadata);
      setDraftCount(getDraftCount()); // Update count
      alert(`Draft saved successfully!\nDraft: ${(draftMetadata as any).saved_draft_type || 'unknown'}\nID: ${savedDraft.draft_id}`);
    } catch (error) {
      alert('Failed to save draft: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  }, [selectedResult, getRawText, selectedDraft]);

  // Load drafts functionality - combine individual drafts into a redundancy session
  const handleLoadDrafts = useCallback((results: DraftSession[]) => {
    if (results.length === 0) return;

    // Create a combined session that mimics a redundancy result
    const combinedResult = {
      id: `combined-${Date.now()}`,
      input: `Combined Drafts (${results.length} drafts)`,
      status: 'completed' as const,
      result: {
        extracted_text: results[0].result.extracted_text, // Use first draft as primary
        model_used: results.map(r => r.result.model_used).join(', '),
        service_type: 'imported-combined',
        tokens_used: 0,
        confidence_score: 1.0,
        metadata: {
          imported_at: new Date().toISOString(),
          is_imported_draft: true,
          redundancy_analysis: {
            enabled: true,
            count: results.length,
            individual_results: results.map((result, index) => ({
              success: true,
              text: result.result.extracted_text,
              model: result.result.model_used,
              confidence: result.result.confidence_score,
              tokens_used: result.result.tokens_used,
              draft_index: index,
              imported_draft_id: result.result.metadata?.original_draft_id
            })),
            consensus_text: results[0].result.extracted_text, // Use first as consensus
            consensus_strategy: 'imported_first',
            confidence_scores: results.map(() => 1.0),
            average_confidence: 1.0
          }
        }
      }
    };

    // Replace current session with the combined result
    setSessionResults([combinedResult]);
    setSelectedResult(combinedResult);
    setSelectedDraft('best'); // Start with best draft view
  }, []);

  return (
    <div className="image-processing-workspace">
      <div className="workspace-nav">
        <AnimatedBorder
          isHovered={homeHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-home" 
            onClick={onExit}
            onMouseEnter={() => setHomeHovered(true)}
            onMouseLeave={() => setHomeHovered(false)}
          >
            Home
          </button>
        </AnimatedBorder>
        <AnimatedBorder
          isHovered={textSchemaHovered}
          strokeWidth={1.5}
        >
          <button 
            className="nav-next" 
            onClick={onNavigateToTextSchema}
            onMouseEnter={() => setTextSchemaHovered(true)}
            onMouseLeave={() => setTextSchemaHovered(false)}
          >
            Text to Schema
          </button>
        </AnimatedBorder>
      </div>
      
      <Allotment defaultSizes={[400, 600]} vertical={false}>
        <Allotment.Pane minSize={250} maxSize={400}>
            <ControlPanel
                stagedFiles={stagedFiles}
                onDrop={onDrop}
                onRemoveStagedFile={removeStagedFile}
                draftCount={draftCount}
                onShowDraftLoader={() => setShowDraftLoader(true)}
                isProcessing={isProcessing}
                onProcess={handleProcess}
                availableModels={availableModels}
                selectedModel={selectedModel}
                onModelChange={setSelectedModel}
                loadingModes={loadingModes}
                availableExtractionModes={availableExtractionModes}
                extractionMode={extractionMode}
                onExtractionModeChange={setExtractionMode}
                enhancementSettings={enhancementSettings}
                onShowEnhancementModal={() => setShowEnhancementModal(true)}
                redundancySettings={redundancySettings}
                onRedundancySettingsChange={setRedundancySettings}
            />
        </Allotment.Pane>
        <Allotment.Pane>
            <ResultsViewer
                isProcessing={isProcessing}
                sessionResults={sessionResults}
                selectedResult={selectedResult}
                onSelectResult={(res) => {
                          setSelectedResult(res);
                    setSelectedDraft('best');
                }}
                isHistoryVisible={isHistoryVisible}
                onToggleHistory={setIsHistoryVisible}
                getCurrentText={getCurrentText}
                getRawText={getRawText}
                isCurrentResultJson={isCurrentResultJson}
                onSaveDraft={handleSaveDraft}
                        selectedDraft={selectedDraft}
                onDraftSelect={setSelectedDraft}
            />
        </Allotment.Pane>
      </Allotment>
      
      {/* Image Enhancement Modal */}
      {showEnhancementModal && (
        <ImageEnhancementModal
          isOpen={showEnhancementModal}
          onClose={() => setShowEnhancementModal(false)}
          enhancementSettings={enhancementSettings}
          onSettingsChange={setEnhancementSettings}
          previewImage={stagedFiles[0]}
        />
      )}

      {/* Draft Loader Modal */}
      <DraftLoader
        isOpen={showDraftLoader}
        onClose={() => setShowDraftLoader(false)}
        onLoadDrafts={handleLoadDrafts}
      />
    </div>
  );
}; 