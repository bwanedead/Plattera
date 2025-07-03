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
import { EnhancementSettings, ProcessingResult, RedundancySettings } from '../../types/imageProcessing';
import { fetchModelsAPI, processFilesAPI } from '../../services/imageProcessingApi';


// Define the type for the component's props, including the onExit callback
interface ImageProcessingWorkspaceProps {
  onExit: () => void;
  onNavigateToTextSchema?: () => void;
}

// --- Main Component ---
export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ onExit, onNavigateToTextSchema }) => {
  const [stagedFiles, setStagedFiles] = useState<File[]>([]);
  const [sessionResults, setSessionResults] = useState<ProcessingResult[]>([]);
  const [selectedResult, setSelectedResult] = useState<ProcessingResult | null>(null);
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
    } catch (error) {
      console.error('Error processing files:', error);
    } finally {
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

    const { result, error } = selectedResult;
    if (error) return error;
    if (!result) return 'No result available';

    const redundancyAnalysis = result.metadata?.redundancy_analysis;
    
    // Use selected consensus strategy if available
    if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
      const consensusText = redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
      // Format JSON as readable text if it's JSON
      return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
    }
    
    // Fallback to original logic
    if (!redundancyAnalysis) {
      const extractedText = result.extracted_text || 'No text available';
      // Format JSON as readable text if it's JSON
      return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
    }

    // CRITICAL DRAFT SELECTION LOGIC
    if (selectedDraft === 'best') {
      const extractedText = result.extracted_text || '';
      // Format JSON as readable text if it's JSON
      return isJsonResult(extractedText) ? formatJsonAsText(extractedText) : extractedText;
    } else if (selectedDraft === 'consensus') {
      const consensusText = redundancyAnalysis.consensus_text || result.extracted_text || '';
      // Format JSON as readable text if it's JSON
      return isJsonResult(consensusText) ? formatJsonAsText(consensusText) : consensusText;
    } else if (typeof selectedDraft === 'number') {
      const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
      if (selectedDraft < individualResults.length) {
        const draftText = individualResults[selectedDraft].text || '';
        // Format JSON as readable text if it's JSON
        return isJsonResult(draftText) ? formatJsonAsText(draftText) : draftText;
      }
    }

    // Fallback to main text
    const fallbackText = result.extracted_text || '';
    return isJsonResult(fallbackText) ? formatJsonAsText(fallbackText) : fallbackText;
  }, [selectedResult, selectedDraft, selectedConsensusStrategy]);

  // Get raw extracted text for JSON tab (without formatting)
  const getRawText = useCallback(() => {
    if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
      return selectedResult?.error || 'No result available';
    }

    const { result, error } = selectedResult;
    if (error) return error;
    if (!result) return 'No result available';

    const redundancyAnalysis = result.metadata?.redundancy_analysis;
    
    // Use selected consensus strategy if available
    if (redundancyAnalysis?.all_consensus_results?.[selectedConsensusStrategy]) {
      return redundancyAnalysis.all_consensus_results[selectedConsensusStrategy].consensus_text;
    }
    
    // Fallback to original logic
    if (!redundancyAnalysis) {
      return result.extracted_text || 'No text available';
    }

    // Draft selection logic for raw text
    if (selectedDraft === 'best') {
      return result.extracted_text || '';
    } else if (selectedDraft === 'consensus') {
      return redundancyAnalysis.consensus_text || result.extracted_text || '';
    } else if (typeof selectedDraft === 'number') {
      const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
      if (selectedDraft < individualResults.length) {
        return individualResults[selectedDraft].text || '';
      }
    }

    return result.extracted_text || '';
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
    if (!selectedResult || selectedResult.status !== 'completed' || !selectedResult.result) {
      alert('No valid result to save');
      return;
    }

    try {
      const content = getRawText();
      
      // Get metadata only for the selected draft
      let draftMetadata: any = {};
      const redundancyAnalysis = selectedResult.result.metadata?.redundancy_analysis;
      
      if (redundancyAnalysis && typeof selectedDraft === 'number') {
        // If it's a specific draft number, get metadata for that draft only
        const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
        
        if (selectedDraft < individualResults.length) {
          const specificDraft = individualResults[selectedDraft];
          draftMetadata = {
            model_used: specificDraft.model || selectedResult.result.metadata?.model_used || 'unknown',
            original_draft_index: selectedDraft,
            saved_draft_type: `draft_${selectedDraft + 1}`,
            confidence_score: specificDraft.confidence || 1.0,
            service_type: selectedResult.result.metadata?.service_type || 'llm'
          };
        }
      } else {
        // For 'best' or 'consensus' drafts, use general metadata
        draftMetadata = {
          model_used: selectedResult.result.metadata?.model_used || 'unknown',
          saved_draft_type: selectedDraft,
          confidence_score: selectedResult.result.metadata?.confidence_score || 1.0,
          service_type: selectedResult.result.metadata?.service_type || 'llm'
        };
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
    const combinedResult: ProcessingResult = {
      input: `Combined Drafts (${results.length} drafts)`,
      status: 'completed' as const,
      result: {
        extracted_text: results[0].result.extracted_text, // Use first draft as primary
        metadata: {
          model_used: results.map(r => r.result.model_used).join(', '),
          service_type: 'imported-combined',
          tokens_used: 0,
          confidence_score: 1.0,
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
                onSelectResult={(res: ProcessingResult) => {
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