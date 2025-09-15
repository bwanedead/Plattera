import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { Allotment } from "allotment";
import "allotment/dist/style.css";
import { ImageEnhancementModal } from './ImageEnhancementModal';
import { DraftLoader } from './DraftLoader';
import { AlignmentPanel } from './AlignmentPanel';
import { ControlPanel } from './ControlPanel';
import { ResultsViewer } from './ResultsViewer';
import { AnimatedBorder } from '../AnimatedBorder';
import { AlignmentTableViewer } from './AlignmentTableViewer';
import { saveDraft, getDraftCount, DraftSession } from '../../utils/draftStorage';
import { useImageProcessing } from '../../hooks/useImageProcessing';
import { useAlignmentState } from '../../hooks/useAlignmentState';
import { useDraftSelection } from '../../hooks/useDraftSelection';
import { useEditableDraft } from '../../hooks/useEditableDraft';
import { useImageProcessingState, useWorkspaceNavigation } from '../../hooks/useWorkspaceState';
import { workspaceStateManager } from '../../services/workspaceStateManager';
import { isJsonResult, formatJsonAsText } from '../../utils/jsonFormatter';
import { getCurrentText, getRawText, getOriginalJsonText, getNormalizedSectionsText, hasNormalizedSections } from '../../utils/textSelectionUtils';
import { FinalDraftSelector } from './FinalDraftSelector';
import { useDossierManager } from '../../hooks/useDossierManager';


interface ImageProcessingWorkspaceProps {
  onExit: () => void;
  onNavigateToTextSchema?: () => void;
}

export const ImageProcessingWorkspace: React.FC<ImageProcessingWorkspaceProps> = ({ 
  onExit, 
  onNavigateToTextSchema 
}) => {
  // State persistence hooks
  const { state: workspaceState, updateState: updateWorkspaceState } = useImageProcessingState();
  const { setActiveWorkspace } = useWorkspaceNavigation();

  // Local UI state (not persisted)
  const [homeHovered, setHomeHovered] = useState(false);
  const [textSchemaHovered, setTextSchemaHovered] = useState(false);
  const [showEnhancementModal, setShowEnhancementModal] = useState(false);
  const [showDraftLoader, setShowDraftLoader] = useState(false);
  const [draftCount, setDraftCount] = useState(0);
  const [showEditedVersion, setShowEditedVersion] = useState(true);

  // Custom hooks for state management
  const imageProcessing = useImageProcessing();
  const alignmentState = useAlignmentState();
  const dossierState = useDossierManager();

  // Debug: Log when dossier state changes
  React.useEffect(() => {
    console.log('🏢 ImageProcessingWorkspace: dossierState updated:', dossierState.state.dossiers);
    if (imageProcessing.selectedDossierId) {
      const selectedDossier = dossierState.state.dossiers.find(d => d.id === imageProcessing.selectedDossierId);
      console.log('🏢 ImageProcessingWorkspace: selected dossier:', selectedDossier);
    }
  }, [dossierState.state.dossiers, imageProcessing.selectedDossierId]);
  
  // Initialize draft selection with persisted state
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>(
    typeof workspaceState.selectedDraft === 'number' ? workspaceState.selectedDraft : 0
  );
  
  // Initialize editable draft hook with new signature
  const editableDraft = useEditableDraft(
    imageProcessing.selectedResult,
    alignmentState.alignmentState.alignmentResult,
    selectedDraft,
    alignmentState.selectedConsensusStrategy
  );

  // Sync state with workspace state manager
  useEffect(() => {
    // Set active workspace when component mounts
    setActiveWorkspace('image-processing');
    
    // Load persisted state into image processing
    if (workspaceState.sessionResults.length > 0) {
      imageProcessing.setSessionResults(workspaceState.sessionResults);
    }
    
    if (workspaceState.selectedResult) {
      imageProcessing.selectResult(workspaceState.selectedResult);
    }
    
    if (workspaceState.alignmentResult) {
      // Update alignment state directly
      alignmentState.alignmentState.alignmentResult = workspaceState.alignmentResult;
    }
    
    if (workspaceState.showHeatmap !== undefined) {
      alignmentState.toggleHeatmap(workspaceState.showHeatmap);
    }
    
    if (workspaceState.showAlignmentPanel !== undefined) {
      if (workspaceState.showAlignmentPanel) {
        // Panel will be shown when alignment result is set
      } else {
        alignmentState.closeAlignmentPanel();
      }
    }
    
    if (workspaceState.showAlignmentTable !== undefined) {
      alignmentState.toggleAlignmentTable(workspaceState.showAlignmentTable);
    }
  }, []);

  // Persist state changes
  useEffect(() => {
    updateWorkspaceState({
      sessionResults: imageProcessing.sessionResults,
      selectedResult: imageProcessing.selectedResult,
      selectedDraft: selectedDraft,
      alignmentResult: alignmentState.alignmentState.alignmentResult,
      isHistoryVisible: workspaceState.isHistoryVisible,
      showHeatmap: alignmentState.alignmentState.showHeatmap,
      showAlignmentPanel: alignmentState.alignmentState.showAlignmentPanel,
      showAlignmentTable: alignmentState.showAlignmentTable,
    });
  }, [
    imageProcessing.sessionResults,
    imageProcessing.selectedResult,
    selectedDraft,
    alignmentState.alignmentState.alignmentResult,
    alignmentState.alignmentState.showHeatmap,
    alignmentState.alignmentState.showAlignmentPanel,
    alignmentState.showAlignmentTable,
  ]);

  // Ensure dossier dropdown refreshes after processing completes (new dossier created)
  useEffect(() => {
    imageProcessing.setOnProcessingComplete(() => {
      try {
        console.log('🔄 Processing completed - refreshing dossiers for dropdown');
        dossierState.loadDossiers();
        // Broadcast a global refresh signal for any listeners (e.g., DossierManager instances)
        try {
          document.dispatchEvent(new CustomEvent('dossiers:refresh'));
        } catch {}
      } catch (e) {
        console.warn('⚠️ Failed to refresh dossiers after processing', e);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [dossierState.loadDossiers]);

  // Handler for final draft selection with state persistence
  const handleFinalDraftSelected = useCallback((finalText: string, metadata: any) => {
    console.log('🎯 Final draft selected in workspace:', {
      finalTextLength: finalText.length,
      metadata
    });
    
    // Update workspace state
    updateWorkspaceState({
      finalDraftText: finalText,
      finalDraftMetadata: metadata
    });
    
    // Sync with text-to-schema workspace
    workspaceStateManager.syncFinalDraft(finalText, metadata);
  }, [updateWorkspaceState]);

  // Text retrieval functions with edit-aware logic
  const getCurrentTextCallback = useCallback(() => {
    // Check if we should show edited version or original based on toggle
    const shouldShowEdited = showEditedVersion && 
      editableDraft.editableDraftState.hasUnsavedChanges && 
      editableDraft.editableDraftState.editedFromDraft === selectedDraft;
    
    if (shouldShowEdited) {
      return editableDraft.editableDraftState.editedDraft.content;
    }
    
    // Use alignment results if available, otherwise fall back to original text
    return getCurrentText({ 
      selectedResult: imageProcessing.selectedResult, 
      selectedDraft, 
      selectedConsensusStrategy: alignmentState.selectedConsensusStrategy,
      alignmentResult: alignmentState.alignmentState.alignmentResult
    });
  }, [editableDraft.editableDraftState, showEditedVersion, selectedDraft, imageProcessing.selectedResult, alignmentState.selectedConsensusStrategy, alignmentState.alignmentState.alignmentResult]);

  const getRawTextCallback = useCallback(() => {
    // Check if we should show edited version or original
    const shouldShowEdited = showEditedVersion && 
      editableDraft.editableDraftState.hasUnsavedChanges && 
      editableDraft.editableDraftState.editedFromDraft === selectedDraft;
    
    if (shouldShowEdited) {
      return editableDraft.editableDraftState.editedDraft.content;
    }
    
    // Use alignment results if available, otherwise fall back to original text
    return getRawText({ 
      selectedResult: imageProcessing.selectedResult, 
      selectedDraft, 
      selectedConsensusStrategy: alignmentState.selectedConsensusStrategy,
      alignmentResult: alignmentState.alignmentState.alignmentResult
    });
  }, [selectedDraft, imageProcessing.selectedResult, editableDraft.editableDraftState, showEditedVersion, alignmentState.selectedConsensusStrategy, alignmentState.alignmentState.alignmentResult]);

  // NEW: Get original JSON text callback (always original LLM output)
  const getOriginalJsonTextCallback = useCallback(() => {
    return getOriginalJsonText({ 
      selectedResult: imageProcessing.selectedResult, 
      selectedDraft,
      selectedConsensusStrategy: alignmentState.selectedConsensusStrategy,
      alignmentResult: alignmentState.alignmentState.alignmentResult
    });
  }, [selectedDraft, imageProcessing.selectedResult, alignmentState.selectedConsensusStrategy, alignmentState.alignmentState.alignmentResult]);

  // NEW: Get normalized sections text callback
  const getNormalizedSectionsTextCallback = useCallback(() => {
    return getNormalizedSectionsText({ 
      selectedResult: imageProcessing.selectedResult, 
      selectedDraft,
      selectedConsensusStrategy: alignmentState.selectedConsensusStrategy,
      alignmentResult: alignmentState.alignmentState.alignmentResult
    });
  }, [selectedDraft, imageProcessing.selectedResult, alignmentState.selectedConsensusStrategy, alignmentState.alignmentState.alignmentResult]);

  // NEW: Check if normalized sections are available
  const hasNormalizedSectionsCallback = useCallback(() => {
    return hasNormalizedSections({ 
      alignmentResult: alignmentState.alignmentState.alignmentResult
    });
  }, [alignmentState.alignmentState.alignmentResult]);

  const isCurrentResultJsonCallback = useCallback(() => {
    const originalJsonText = getOriginalJsonTextCallback();
    return isJsonResult(originalJsonText);
  }, [getOriginalJsonTextCallback]);

  // Reset draft selection when result changes, honoring selected_draft_index if provided
  useEffect(() => {
    if (imageProcessing.selectedResult) {
      const idx = imageProcessing.selectedResult?.result?.metadata?.selected_draft_index;
      console.log('🧭 Workspace result change:', {
        hasResult: true,
        selected_draft_index: idx,
        prevSelectedDraft: selectedDraft
      });
      setSelectedDraft(typeof idx === 'number' ? idx : 0);
      alignmentState.resetAlignmentState();
    }
  }, [imageProcessing.selectedResult]);

  // Reset editing when alignment result changes
  useEffect(() => {
    if (alignmentState.alignmentState.alignmentResult) {
      editableDraft.resetToOriginal();
    }
  }, [alignmentState.alignmentState.alignmentResult]);

  // Initialize draft count
  useEffect(() => {
    setDraftCount(getDraftCount());
  }, []);



  // Save draft functionality
  const handleSaveDraft = () => {
    if (!imageProcessing.selectedResult || imageProcessing.selectedResult.status !== 'completed' || !imageProcessing.selectedResult.result) {
      alert('No valid result to save');
      return;
    }

    try {
      // FIXED: Use the content from the editable draft state, which includes any user edits.
      // This ensures we save the most up-to-date version of the text, including any edits
      // made in the confidence heatmap viewer.
      const content = editableDraft.editableDraftState.editedDraft.content;
      
      // Get metadata for the selected draft
      let draftMetadata: any = {};
      const redundancyAnalysis = imageProcessing.selectedResult.result.metadata?.redundancy_analysis;
      
      if (redundancyAnalysis && typeof selectedDraft === 'number') {
        const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
        
        if (selectedDraft < individualResults.length) {
          const specificDraft = individualResults[selectedDraft];
          draftMetadata = {
            model_used: specificDraft.model || imageProcessing.selectedResult.result.metadata?.model_used || 'unknown',
            original_draft_index: selectedDraft,
            saved_draft_type: `draft_${selectedDraft + 1}`,
            confidence_score: specificDraft.confidence || 1.0,
            service_type: imageProcessing.selectedResult.result.metadata?.service_type || 'llm'
          };
        }
      } else {
        draftMetadata = {
          model_used: imageProcessing.selectedResult.result.metadata?.model_used || 'unknown',
          saved_draft_type: selectedDraft,
          confidence_score: imageProcessing.selectedResult.result.metadata?.confidence_score || 1.0,
          service_type: imageProcessing.selectedResult.result.metadata?.service_type || 'llm'
        };
      }
      
      const savedDraft = saveDraft(content, draftMetadata.model_used || 'unknown', draftMetadata);
      setDraftCount(getDraftCount());
      alert(`Draft saved successfully!\nDraft: ${draftMetadata.saved_draft_type || 'unknown'}\nID: ${savedDraft.draft_id}`);
    } catch (error) {
      alert('Failed to save draft: ' + (error instanceof Error ? error.message : 'Unknown error'));
    }
  };

  // Load drafts functionality
  const handleLoadDrafts = (results: DraftSession[]) => {
    if (results.length === 0) return;

    // Create a combined session that mimics a redundancy result
    const combinedResult = {
      input: `Combined Drafts (${results.length} drafts)`,
      status: 'completed' as const,
      result: {
        extracted_text: results[0].result.extracted_text,
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
            consensus_text: results[0].result.extracted_text,
            consensus_strategy: 'imported_first',
            confidence_scores: results.map(() => 1.0),
            average_confidence: 1.0
          }
        }
      }
    };

    imageProcessing.setSessionResults([combinedResult]);
    imageProcessing.selectResult(combinedResult);
    alignmentState.resetAlignmentState();
  };

  // NEW: State for final draft


  // Calculate Allotment sizes based on alignment panel visibility
  const getAllotmentSizes = () => {
    if (alignmentState.alignmentState.showAlignmentPanel) {
      return [300, 250, 450]; // ControlPanel, AlignmentPanel, ResultsViewer
    }
    return [300, 700]; // ControlPanel, ResultsViewer
  };

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
      
      <Allotment defaultSizes={getAllotmentSizes()} vertical={false}>
        <Allotment.Pane minSize={250} maxSize={400}>
            <ControlPanel
            stagedFiles={imageProcessing.stagedFiles}
            onDrop={imageProcessing.onDrop}
            onRemoveStagedFile={imageProcessing.removeStagedFile}
                draftCount={draftCount}
                onShowDraftLoader={() => setShowDraftLoader(true)}
            isProcessing={imageProcessing.isProcessing}
            onProcess={imageProcessing.handleProcess}
            availableModels={imageProcessing.availableModels}
            selectedModel={imageProcessing.selectedModel}
            onModelChange={imageProcessing.setSelectedModel}
            loadingModes={imageProcessing.loadingModes}
            availableExtractionModes={imageProcessing.availableExtractionModes}
            extractionMode={imageProcessing.extractionMode}
            onExtractionModeChange={imageProcessing.setExtractionMode}
            enhancementSettings={imageProcessing.enhancementSettings}
                onShowEnhancementModal={() => setShowEnhancementModal(true)}
            redundancySettings={imageProcessing.redundancySettings}
            onRedundancySettingsChange={imageProcessing.setRedundancySettings}
            // DOSSIER SUPPORT
            selectedDossierId={imageProcessing.selectedDossierId}
            onDossierChange={imageProcessing.setSelectedDossierId}
            dossiers={dossierState.state.dossiers}
            selectedSegmentId={imageProcessing.selectedSegmentId}
            onSegmentChange={imageProcessing.setSelectedSegmentId}
            />
        </Allotment.Pane>
        
        {alignmentState.alignmentState.showAlignmentPanel && (
          <Allotment.Pane minSize={200} maxSize={300}>
            <AlignmentPanel
              alignmentResult={alignmentState.alignmentState.alignmentResult}
              showHeatmap={alignmentState.alignmentState.showHeatmap}
              onToggleHeatmap={alignmentState.toggleHeatmap}
              onClose={alignmentState.closeAlignmentPanel}
              onToggleAlignmentTable={alignmentState.toggleAlignmentTable}
            />
          </Allotment.Pane>
        )}
        
        {alignmentState.showAlignmentTable && alignmentState.alignmentState.alignmentResult && (
          <Allotment.Pane minSize={200} maxSize={300}>
            <AlignmentTableViewer
              alignmentResult={alignmentState.alignmentState.alignmentResult}
              onClose={() => alignmentState.toggleAlignmentTable(false)}
            />
          </Allotment.Pane>
        )}
        
        <Allotment.Pane>
            <ResultsViewer
            isProcessing={imageProcessing.isProcessing}
            sessionResults={imageProcessing.sessionResults}
            selectedResult={imageProcessing.selectedResult}
            onSelectResult={(res: any) => {
              imageProcessing.selectResult(res);
              const idx = res?.result?.metadata?.selected_draft_index;
              setSelectedDraft(typeof idx === 'number' ? idx : 0); // Honor selected draft index from DossierManager
              alignmentState.resetAlignmentState();
                }}
                            isHistoryVisible={workspaceState.isHistoryVisible}
            onToggleHistory={(visible) => updateWorkspaceState({ isHistoryVisible: visible })}
            getCurrentText={getCurrentTextCallback}
            getRawText={getRawTextCallback}
            getOriginalJsonText={getOriginalJsonTextCallback}
            getNormalizedSectionsText={getNormalizedSectionsTextCallback}
            hasNormalizedSections={hasNormalizedSectionsCallback}
            isCurrentResultJson={isCurrentResultJsonCallback}
                onSaveDraft={handleSaveDraft}
            selectedDraft={selectedDraft}
            onDraftSelect={setSelectedDraft}
            alignmentResult={alignmentState.alignmentState.alignmentResult}
            showHeatmap={alignmentState.alignmentState.showHeatmap}
            onAlign={() => alignmentState.handleAlign(imageProcessing.selectedResult)}
            isAligning={alignmentState.alignmentState.isAligning}
            onTextUpdate={(newText: string) => {
              // This is called when text is edited in the heatmap
              console.log('Text updated in heatmap:', newText);
              // The text update is handled by the editableDraft hook automatically
            }}
            onApplyEdit={(blockIndex: number, tokenIndex: number, newValue: string, editType?: 'alternative_selection' | 'manual_edit') => {
              // Convert editType to alternatives array format
              const alternatives = editType === 'alternative_selection' ? [newValue] : undefined;
              editableDraft.applyEdit(blockIndex, tokenIndex, newValue, alternatives);
            }}
            editableDraftState={{
              hasUnsavedChanges: editableDraft.editableDraftState.hasUnsavedChanges,
              canUndo: editableDraft.canUndo,
              canRedo: editableDraft.canRedo,
              editedDraft: editableDraft.editableDraftState.editedDraft,
              editedFromDraft: editableDraft.editableDraftState.editedFromDraft,
              editHistory: editableDraft.editableDraftState.editHistory
            }}
            onUndoEdit={editableDraft.undoEdit}
            onRedoEdit={editableDraft.redoEdit}
            onResetToOriginal={editableDraft.resetToOriginal}
            onSaveAsOriginal={editableDraft.saveAsOriginal}
            showEditedVersion={showEditedVersion}
            onToggleEditedVersion={() => setShowEditedVersion(!showEditedVersion)}
            onFinalDraftSelected={handleFinalDraftSelected}
            />
        </Allotment.Pane>
      </Allotment>
      
      {/* Image Enhancement Modal */}
      {showEnhancementModal && (
        <ImageEnhancementModal
          isOpen={showEnhancementModal}
          onClose={() => setShowEnhancementModal(false)}
          enhancementSettings={imageProcessing.enhancementSettings}
          onSettingsChange={imageProcessing.setEnhancementSettings}
          previewImage={imageProcessing.stagedFiles[0]}
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