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

import React, { useState, useCallback, useEffect, useRef, useLayoutEffect } from 'react';
import { useDropzone } from 'react-dropzone';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ParcelTracerLoader } from './ParcelTracerLoader';
import { ImageEnhancementModal } from './ImageEnhancementModal';
import { DraftSelector } from './DraftSelector';
import { AnimatedBorder } from './AnimatedBorder';
import { HeatmapToggle } from './HeatmapToggle';
import { CopyButton } from './CopyButton';
import { AlignmentAnalysisPanel } from './AlignmentAnalysisPanel';
import { AlignmentColoredText } from './AlignmentColoredText';
import { DraftLoader } from './DraftLoader';
import { 
  isJsonResult, 
  formatJsonAsText, 
  formatJsonPretty,
  getWordCount 
} from '../utils/jsonFormatter';
import { saveDraft, getDraftCount, DraftSession } from '../utils/draftStorage';

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

// Enhancement settings interface
interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

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

const STATS_PANEL_WIDTH = 350;

// --- Main Component ---
// Version: v2.1 - BioPython Visualizer Integration
export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ onExit, onNavigateToTextSchema }) => {
  /*
  🔴 CRITICAL STATE MANAGEMENT DOCUMENTATION 🔴
  =============================================
  
  EXISTING CRITICAL STATE (DO NOT MODIFY):
  - selectedResult: Contains redundancy_analysis data needed for heatmap
  - selectedDraft: Controls which text is displayed (affects heatmap display)
  - redundancySettings: Controls redundancy processing (affects heatmap data availability)
  
  REQUIRED HEATMAP STATE ADDITIONS:
  ================================
  
  ADD THESE STATE VARIABLES AFTER selectedDraft:
  
  const [isHeatmapEnabled, setIsHeatmapEnabled] = useState(false);
  const [editedText, setEditedText] = useState<string>('');
  const [isTextEdited, setIsTextEdited] = useState(false);
  
  CRITICAL CALLBACK FUNCTIONS TO ADD:
  ==================================
  
  const handleTextUpdate = useCallback((newText: string) => {
    setEditedText(newText);
    setIsTextEdited(true);
    // Optional: Mark result as edited in metadata
  }, []);
  
  const handleHeatmapToggle = useCallback((enabled: boolean) => {
    setIsHeatmapEnabled(enabled);
    if (!enabled) {
      // Reset edited state when disabling heatmap
      setIsTextEdited(false);
      setEditedText('');
    }
  }, []);
  
  CRITICAL INTEGRATION POINTS:
  ============================
  
  1. getCurrentText() function MUST be modified to return editedText when available:
     - If isTextEdited && editedText: return editedText
     - Otherwise: return normal draft text logic
  
  2. DraftSelector must coordinate with heatmap state:
     - When draft changes, reset edited state if needed
     - Heatmap display must update to show selected draft
  
  3. Result selection must reset heatmap state:
     - When selectedResult changes, reset isHeatmapEnabled
     - Clear any edited text state
  */
  
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
  const [activeTab, setActiveTab] = useState('text');
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
  
  // Alignment state
  const [alignmentData, setAlignmentData] = useState<any>(null);
  const [showAlignmentPanel, setShowAlignmentPanel] = useState(false);
  const [isAlignmentMode, setIsAlignmentMode] = useState(false);
  const [isAlignmentLoading, setIsAlignmentLoading] = useState(false);

  // Draft management state
  const [showDraftLoader, setShowDraftLoader] = useState(false);
  const [draftCount, setDraftCount] = useState(0);

  // Debug logging to help with redundancySettings issue
  console.log('🔧 ImageProcessingWorkspace rendered with redundancySettings:', redundancySettings);

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

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop: onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.webp']
    },
    multiple: true
  });

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
  
  const removeStagedFile = (fileName: string) => {
    setStagedFiles(prev => prev.filter(f => f.name !== fileName));
  };

  useEffect(() => {
    fetchModelsAPI().then(setAvailableModels);
    
    // Load extraction modes
    const loadExtractionModes = async () => {
      try {
        const response = await fetch('http://localhost:8000/api/process/types')
        const data = await response.json()
        
        if (data.status === 'success' && data.processing_types?.['image-to-text']?.extraction_modes) {
          console.log('Extraction modes API response:', data.processing_types['image-to-text'].extraction_modes)
          console.log('Is array?', Array.isArray(data.processing_types['image-to-text'].extraction_modes))
          console.log('Type:', typeof data.processing_types['image-to-text'].extraction_modes)
          console.log('Keys:', Object.keys(data.processing_types['image-to-text'].extraction_modes))
          setAvailableExtractionModes(data.processing_types['image-to-text'].extraction_modes)
        } else {
          console.log('API response:', data)
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

  const handleEnhancementChange = useCallback((setting: keyof EnhancementSettings, value: number) => {
    setEnhancementSettings(prev => ({
      ...prev,
      [setting]: value
    }));
  }, []);

  /*
  🔴 CRITICAL TEXT RETRIEVAL FUNCTION - CORE HEATMAP INTEGRATION POINT 🔴
  =======================================================================
  
  This function determines which text is displayed in the results viewer.
  The heatmap feature DEPENDS on this function working correctly.
  
  CURRENT LOGIC (MUST BE PRESERVED):
  1. Error handling for failed results
  2. Fallback to main text when no redundancy data
  3. Draft selection logic (best/consensus/individual)
  4. Graceful fallbacks for missing data
  
  REQUIRED HEATMAP MODIFICATION:
  =============================
  
  ADD THIS LOGIC AT THE BEGINNING (after error check):
  
  // HEATMAP INTEGRATION: Return edited text if available
  if (isTextEdited && editedText) {
    return editedText;
  }
  
  CRITICAL DEPENDENCIES:
  - isTextEdited state (tracks if user has made edits via heatmap)
  - editedText state (contains user's edited version)
  - selectedDraft state (determines which draft to show in heatmap)
  - redundancyAnalysis data (provides word confidence for heatmap coloring)
  
  HEATMAP WORKFLOW:
  1. getCurrentText() provides base text to ConfidenceHeatmapViewer
  2. User edits words via heatmap interface
  3. handleTextUpdate() callback sets editedText and isTextEdited
  4. getCurrentText() returns editedText on subsequent calls
  5. Normal <pre> view and heatmap view both use same text source
  
  ⚠️  DO NOT MODIFY THE EXISTING DRAFT SELECTION LOGIC
  ⚠️  DO NOT CHANGE THE FALLBACK BEHAVIOR
  ⚠️  ONLY ADD THE EDITED TEXT CHECK AT THE TOP
  */
  const getCurrentText = useCallback(() => {
    if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
      return selectedResult?.error || 'No result available';
    }

    const redundancyAnalysis = selectedResult.result?.metadata?.redundancy_analysis;
    
    // 🆕 Use selected consensus strategy if available
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

  const handleDraftSelect = useCallback((draft: number | 'consensus' | 'best') => {
    setSelectedDraft(draft);
  }, []);

  const handleHeatmapToggle = useCallback(async (enabled: boolean) => {
    console.log('🔥 FIRE BUTTON CLICKED! Starting alignment analysis...');
    console.log('🔥 Fire button params:', { enabled });
    console.log('🔥 selectedResult:', selectedResult);
    
    // Set loading state
    setIsAlignmentLoading(true);
    
    try {
      const redundancyAnalysis = selectedResult?.result?.metadata?.redundancy_analysis;
      const extractedText = getCurrentText();
      
      console.log('🔥 redundancyAnalysis:', redundancyAnalysis);
      console.log('🔥 extractedText length:', extractedText?.length);
      
      if (!redundancyAnalysis) {
        console.error('🔥 No redundancy analysis data available');
        alert('No redundancy analysis data available for alignment');
        setIsAlignmentLoading(false);
        return;
      }

      // Convert redundancy analysis to draft format for alignment API
      console.log('🔥 Converting redundancy data to drafts...');
      const drafts = [];
      const individualResults = redundancyAnalysis.individual_results || [];
      
      console.log('🔥 individualResults:', individualResults);
      
      for (let i = 0; i < individualResults.length; i++) {
        const result = individualResults[i];
        if (result.success) {
          drafts.push({
            draft_id: `Draft_${i + 1}`,
            blocks: [
              {
                id: "legal_text",
                text: result.text || ""
              }
            ]
          });
        }
      }

      if (drafts.length < 2) {
        console.log('🔥 Creating demo drafts (less than 2 successful drafts)');
        // Create demo drafts for single result
        drafts.push(
          {
            draft_id: "Draft_1",
            blocks: [{ id: "legal_text", text: extractedText }]
          },
          {
            draft_id: "Draft_2", 
            blocks: [{ id: "legal_text", text: extractedText.replace(/the/g, "this").replace(/and/g, "plus") }]
          }
        );
      }

      console.log('🔥 Final drafts for alignment:', drafts.length, 'drafts');
      console.log('🔥 Draft preview:', drafts.map(d => ({ id: d.draft_id, textLength: d.blocks[0].text.length })));

      // Call the alignment API
      console.log('🔥 Calling alignment API...');
      const response = await fetch('http://localhost:8000/api/alignment/align-drafts', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          drafts: drafts,
          generate_visualization: false, // We don't need the HTML visualization
          consensus_strategy: "highest_confidence"
        }),
      });

      console.log('🔥 Alignment API response status:', response.status);

      if (response.ok) {
        const alignmentResult = await response.json();
        console.log('🔥 Alignment result:', alignmentResult);
        
        if (alignmentResult.success) {
          console.log('🔥 Alignment successful! Setting state...');
          console.log('🔥 About to call setAlignmentData with:', alignmentResult);
          console.log('🔥 About to call setShowAlignmentPanel(true)');
          console.log('🔥 About to call setIsAlignmentMode(true)');
          
          setAlignmentData(alignmentResult);
          setShowAlignmentPanel(true);
          setIsAlignmentMode(true);
          
          console.log('🔥 State setters called successfully!');
          console.log('🧬 Alignment analysis completed:', alignmentResult);
        } else {
          console.error('🔥 Alignment failed:', alignmentResult.error);
          alert(`Alignment analysis failed: ${alignmentResult.error}`);
        }
      } else {
        const errorText = await response.text();
        console.error('🔥 Alignment API error:', errorText);
        alert('Failed to perform alignment analysis. Check console for details.');
      }
    } catch (error) {
      console.error('🔥 Error calling alignment API:', error);
      console.error('🔥 Full error details:', error);
      alert('Failed to connect to alignment service');
    } finally {
      // Always clear loading state
      setIsAlignmentLoading(false);
    }
  }, [selectedResult, getCurrentText]);

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
        };
      }
      
      const savedDraft = saveDraft(content, draftMetadata.model_used, draftMetadata);
      setDraftCount(getDraftCount()); // Update count
      alert(`Draft saved successfully!\nDraft: ${draftMetadata.saved_draft_type}\nID: ${savedDraft.draft_id}`);
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

  const textViewerRef = useRef<HTMLDivElement>(null);
  const [statsPanelLeft, setStatsPanelLeft] = useState(0);

  // Update position on mount, window resize, and Allotment pane resize
  useLayoutEffect(() => {
    function updateLeft() {
      if (textViewerRef.current) {
        const rect = textViewerRef.current.getBoundingClientRect();
        setStatsPanelLeft(rect.left - STATS_PANEL_WIDTH);
      } else {
        setStatsPanelLeft(0);
      }
    }
    updateLeft();
    window.addEventListener('resize', updateLeft);

    // Use ResizeObserver for dynamic pane resizing
    let observer: ResizeObserver | null = null;
    if (textViewerRef.current && 'ResizeObserver' in window) {
      observer = new ResizeObserver(() => {
        updateLeft();
      });
      observer.observe(textViewerRef.current);
    }

    return () => {
      window.removeEventListener('resize', updateLeft);
      if (observer && textViewerRef.current) {
        observer.unobserve(textViewerRef.current);
      }
    };
  }, [isHistoryVisible, selectedResult, activeTab]);

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
          <div className="control-panel">
            <div className="panel-header">
              <h2>Image to Text</h2>
            </div>
            
            <div className="import-section">
              <label>Import Files</label>
              
              {/* Load Saved Drafts Button */}
              <div className="draft-loader-section">
                <button 
                  className="load-drafts-button"
                  onClick={() => setShowDraftLoader(true)}
                  disabled={draftCount === 0}
                >
                  📁 Load Saved Drafts ({draftCount})
                </button>
              </div>
              
              <div 
                {...getRootProps()} 
                className={`file-drop-zone ${isDragActive ? 'drag-active' : ''} ${stagedFiles.length > 0 ? 'has-files' : ''}`}
              >
                <input {...getInputProps()} />
                <div className="drop-zone-content">
                  {stagedFiles.length === 0 ? (
                    <>
                      <div className="drop-icon">📁</div>
                      <div className="drop-text">
                        <strong>Click to select files</strong> or drag and drop
                      </div>
                      <div className="drop-hint">PNG, JPG, JPEG, GIF, BMP, WebP</div>
                    </>
                  ) : (
                    <>
                      <div className="files-count">{stagedFiles.length} file{stagedFiles.length > 1 ? 's' : ''} ready</div>
                      <div className="drop-hint">Click to add more or drag additional files</div>
                    </>
                  )}
                </div>
              </div>
              
              {stagedFiles.length > 0 && (
                <div className="staged-files">
                  {stagedFiles.map((file, index) => (
                    <div key={index} className="staged-file">
                      <span className="file-name">{file.name}</span>
                      <button 
                        className="remove-file"
                        onClick={() => removeStagedFile(file.name)}
                      >
                        ×
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="model-section">
              <label>AI Model</label>
              <select 
                value={selectedModel} 
                onChange={(e) => setSelectedModel(e.target.value)}
                className="model-selector"
              >
                <option value="gpt-o4-mini">GPT-o4-mini (Recommended)</option>
                <option value="gpt-4o">GPT-4o</option>
                <option value="o3">o3 (Premium)</option>
                <option value="gpt-4">GPT-4</option>
              </select>
            </div>

            <div className="extraction-section">
              <label>Extraction Mode</label>
              <select 
                value={extractionMode} 
                onChange={(e) => setExtractionMode(e.target.value)}
                className="extraction-selector"
                disabled={loadingModes}
              >
                {loadingModes ? (
                  <option>Loading modes...</option>
                ) : (
                  Object.entries(availableExtractionModes).map(([modeId, modeInfo]) => (
                    <option key={modeId} value={modeId}>
                      {modeInfo.name} - {modeInfo.description}
                    </option>
                  ))
                )}
              </select>
            </div>

            <div className="enhancement-section">
              <button 
                className="enhancement-modal-btn"
                onClick={() => setShowEnhancementModal(true)}
                disabled={isProcessing}
              >
                🎨 Image Enhancement
              </button>
              <small className="enhancement-hint">
                Current: C:{enhancementSettings.contrast.toFixed(1)} S:{enhancementSettings.sharpness.toFixed(1)} B:{enhancementSettings.brightness.toFixed(1)} Col:{enhancementSettings.color.toFixed(1)}
              </small>
            </div>

            <div className="redundancy-section">
              <label>Redundancy Filter</label>
              <div className="redundancy-controls">
                <div className="redundancy-toggle">
                  <input
                    type="checkbox"
                    id="redundancy-enabled"
                    checked={redundancySettings.enabled}
                    onChange={(e) => setRedundancySettings(prev => ({
                      ...prev,
                      enabled: e.target.checked
                    }))}
                  />
                  <label htmlFor="redundancy-enabled">Enable Redundancy</label>
                </div>
                
                {redundancySettings.enabled && (
                  <>
                    <div className="redundancy-slider-group">
                      <label htmlFor="redundancy-count">
                        Redundancy Count: {redundancySettings.count}
                      </label>
                      <input
                        type="range"
                        id="redundancy-count"
                        min="1"
                        max="10"
                        value={redundancySettings.count}
                        onChange={(e) => setRedundancySettings(prev => ({
                          ...prev,
                          count: parseInt(e.target.value)
                        }))}
                        className="redundancy-slider"
                      />
                      <div className="redundancy-hint">
                        {redundancySettings.count === 1 ? 'No redundancy' : 
                         redundancySettings.count <= 3 ? 'Light redundancy' :
                         redundancySettings.count <= 5 ? 'Medium redundancy' : 'Heavy redundancy'}
                      </div>
                    </div>
                  </>
                )}
              </div>
            </div>

            <div className="process-section">
              <button 
                className={`process-button ${isProcessing ? 'processing' : ''}`}
                onClick={handleProcess}
                disabled={stagedFiles.length === 0 || isProcessing}
              >
                {isProcessing ? 'Processing...' : `Process ${stagedFiles.length} File${stagedFiles.length !== 1 ? 's' : ''}`}
              </button>
            </div>
          </div>
        </Allotment.Pane>
        <Allotment.Pane>
          <div className="results-area" style={{ width: '100%', height: '100%' }}>
            <Allotment defaultSizes={[300, 700]} vertical={false}>
              {isHistoryVisible && (
                <Allotment.Pane minSize={200} maxSize={500}>
                  <div className="results-history-panel visible">
                    <div className="history-header">
                      <h4>Session Log</h4>
                      <button onClick={() => setIsHistoryVisible(false)}>‹</button>
                    </div>
                    <div className="history-list-items">
                      {sessionResults.map((res, i) => (
                        <div key={i} className={`log-item ${selectedResult === res ? 'selected' : ''} ${res.status}`} onClick={() => {
                          setSelectedResult(res);
                          setSelectedDraft('best'); // Reset to best draft when switching results
                        }}>
                          <span className={`log-item-status-dot ${res.status}`}></span>
                          {res.input}
                        </div>
                      ))}
                    </div>
                  </div>
                </Allotment.Pane>
              )}
              <Allotment.Pane>
                <div className="results-viewer-panel">
                  {!isHistoryVisible && <button className="history-toggle-button" onClick={() => setIsHistoryVisible(true)}>›</button>}
                  {isProcessing && (
                    <div className="loading-view">
                      <ParcelTracerLoader />
                      <h4>Tracing Parcels...</h4>
                      <p>Analyzing document geometry.</p>
                    </div>
                  )}
                  {!isProcessing && !selectedResult && (
                     <div className="placeholder-view">
                        <p>Your results will appear here.</p>
                    </div>
                  )}
                  {!isProcessing && selectedResult && (
                    <div className="result-display-area">
                      <CopyButton 
                        onCopy={() => {
                          if (activeTab === 'text') {
                            navigator.clipboard.writeText(getCurrentText());
                          } else if (activeTab === 'json') {
                            navigator.clipboard.writeText(formatJsonPretty(getRawText()));
                          } else if (activeTab === 'metadata') {
                            navigator.clipboard.writeText(selectedResult.status === 'completed' ? JSON.stringify(selectedResult.result?.metadata, null, 2) : 'No metadata available for failed processing.');
                          }
                        }}
                        title={`Copy ${activeTab}`}
                        style={{
                          position: 'absolute',
                          top: '5rem',
                          left: '-3rem',
                          zIndex: 20
                        }}
                      />
                      
                      <DraftSelector
                        redundancyAnalysis={selectedResult.result?.metadata?.redundancy_analysis}
                        onDraftSelect={handleDraftSelect}
                        selectedDraft={selectedDraft}
                      />
                      
                      <HeatmapToggle
                        isEnabled={false}
                        onToggle={handleHeatmapToggle}
                        hasRedundancyData={!!selectedResult?.result?.metadata?.redundancy_analysis}
                        isLoading={isAlignmentLoading}
                        redundancyAnalysis={selectedResult?.result?.metadata?.redundancy_analysis}
                      />
                      
                      <div className="result-tabs">
                          <button className={activeTab === 'text' ? 'active' : ''} onClick={() => setActiveTab('text')}>📄 Text</button>
                          {isCurrentResultJson() && (
                            <button className={activeTab === 'json' ? 'active' : ''} onClick={() => setActiveTab('json')}>🔧 JSON</button>
                          )}
                          <button className={activeTab === 'metadata' ? 'active' : ''} onClick={() => setActiveTab('metadata')}>📊 Metadata</button>
                      </div>
                      
                      <div className="result-tab-content">
                          {activeTab === 'text' && (
                            <div
                              className="text-viewer-pane"
                              ref={textViewerRef}
                              style={{ height: '100%' }}
                            >
                              <AlignmentColoredText
                                text={getCurrentText()}
                                confidenceData={alignmentData?.confidence_results}
                                isAlignmentMode={isAlignmentMode}
                              />
                            </div>
                          )}
                          {activeTab === 'json' && isCurrentResultJson() && (
                            <div className="json-display">
                              <div className="json-actions">
                                <button 
                                  className="save-draft-button"
                                  onClick={handleSaveDraft}
                                  title="Save this draft for future alignment testing"
                                >
                                  💾 Save Draft
                                </button>
                              </div>
                              <pre className="json-content">{formatJsonPretty(getRawText())}</pre>
                            </div>
                          )}
                          {activeTab === 'metadata' && (
                            <div className="metadata-display">
                              <pre>{selectedResult.status === 'completed' ? JSON.stringify(selectedResult.result?.metadata, null, 2) : 'No metadata available for failed processing.'}</pre>
                            </div>
                          )}
                      </div>
                    </div>
                  )}
                  {/* Floating stats panel */}
                  {showAlignmentPanel && (
                    <div
                      className="alignment-analysis-panel-floating"
                      style={{
                        position: 'fixed',
                        top: 0,
                        left: statsPanelLeft,
                        width: STATS_PANEL_WIDTH,
                        height: '100%',
                        zIndex: 100,
                        pointerEvents: 'auto'
                      }}
                    >
                      <AlignmentAnalysisPanel
                        alignmentData={alignmentData}
                        isVisible={showAlignmentPanel}
                        onClose={() => {
                          setShowAlignmentPanel(false);
                          setIsAlignmentMode(false);
                          setAlignmentData(null);
                        }}
                      />
                    </div>
                  )}
                </div>
              </Allotment.Pane>
            </Allotment>
          </div>
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