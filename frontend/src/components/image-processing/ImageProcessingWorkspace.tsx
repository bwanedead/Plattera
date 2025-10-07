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
import { isJsonResult, formatJsonAsText, canParseJson } from '../../utils/jsonFormatter';
import { getCurrentText, getRawText, getOriginalJsonText, getNormalizedSectionsText, hasNormalizedSections } from '../../utils/textSelectionUtils';
import { FinalDraftSelector } from './FinalDraftSelector';
import { useDossierManager } from '../../hooks/useDossierManager';
import { saveDossierEditAPI } from '../../services/imageProcessingApi';


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

  // Auto-refresh dossiers when processing completes
  const handleProcessingComplete = useCallback(() => {
    console.log('📡 Dispatching dossiers:refresh event after processing completion');
    document.dispatchEvent(new Event('dossiers:refresh'));
  }, []);

  // Track selected dossier for processing
  const [selectedDossierId, setSelectedDossierId] = React.useState<string | null>(null);

  // Custom hooks for state management
  const imageProcessing = useImageProcessing({
    onProcessingComplete: handleProcessingComplete,
    selectedDossierId: selectedDossierId
  });
  const alignmentState = useAlignmentState();
  const dossierState = useDossierManager();

  // Send an immediate refresh event when processing starts
  useEffect(() => {
    if (imageProcessing.isProcessing) {
      console.log('📡 Processing started - dispatching dossiers:refresh');
      document.dispatchEvent(new Event('dossiers:refresh'));
    }
  }, [imageProcessing.isProcessing]);

  // Debug: Log when dossier state changes
  React.useEffect(() => {
    console.log('🏢 ImageProcessingWorkspace: dossierState updated:', dossierState.state.dossiers);
    if (selectedDossierId) {
      const selectedDossier = dossierState.state.dossiers.find(d => d.id === selectedDossierId);
      console.log('🏢 ImageProcessingWorkspace: selected dossier:', selectedDossier);
    }
  }, [dossierState.state.dossiers, selectedDossierId]);
  
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
        // Defer dossier loading to avoid React state update during render
        setTimeout(() => {
          dossierState.loadDossiers();
        }, 0);
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

  // Save edited content to v2/Av2/consensus, preferring provided sections from heatmap
  const handleSaveEditedContent = useCallback(async (payload?: { sections?: Array<{ id: number | string; body: string }>; text?: string }) => {
    const dossierId = selectedDossierId || imageProcessing.selectedResult?.result?.metadata?.dossier_id;
    const transcriptionId = imageProcessing.selectedResult?.result?.metadata?.transcription_id;
    if (!dossierId || !transcriptionId) {
      alert('Missing dossier or transcription context.');
      return;
    }

    // Prefer sections supplied by heatmap; fallback to current edited buffer
    const sections = (payload?.sections && payload.sections.length > 0)
      ? payload.sections
      : (() => {
          const blocks = editableDraft.editableDraftState.editedDraft.blockTexts;
          return (blocks && blocks.length > 0)
            ? blocks.map((body, i) => ({ id: i + 1, body }))
            : [{ id: 1, body: editableDraft.editableDraftState.editedDraft.content }];
        })();

    try {
      const meta = imageProcessing.selectedResult?.result?.metadata || {};
      const isConsensusSelected = !!meta?.is_consensus_selected || (typeof selectedDraft === 'string' && selectedDraft === 'consensus');
      const consensusType = meta?.selected_versioned_draft_id && /_consensus_alignment$/.test(String(meta.selected_versioned_draft_id))
        ? 'alignment'
        : (meta?.selected_versioned_draft_id && /_consensus_llm$/.test(String(meta.selected_versioned_draft_id)) ? 'llm' : undefined);

      // Decide where edits funnel: alignment Av2 if heatmap is shown or viewing alignment draft; else raw/consensus v2
      const saveParams: any = {
        dossierId: String(dossierId),
        transcriptionId: String(transcriptionId),
        editedSections: sections,
      };
      const selectedId = String(meta?.selected_versioned_draft_id || '');
      const isAlignmentId = /_draft_\d+(?:_v[12])?$/.test(selectedId);
      if (alignmentState.alignmentState.showHeatmap || isAlignmentId) {
        // Prefer deriving draft number from the currently selected versioned draft id if alignment
        let draftNumberFromId: number | null = null;
        try {
          const m = selectedId.match(/_draft_(\d+)(?:_v[12])?$/);
          if (m) draftNumberFromId = parseInt(m[1], 10);
        } catch {}
        const oneBased = draftNumberFromId || ((typeof selectedDraft === 'number') ? (selectedDraft + 1) : 1);
        // alignmentDraftIndex is 0-based in backend signature
        saveParams.alignmentDraftIndex = Math.max(0, oneBased - 1);
      } else if (isConsensusSelected && consensusType) {
        saveParams.consensusType = consensusType;
      } else if (typeof selectedDraft === 'number') {
        saveParams.draftIndex = selectedDraft;
      }

      await saveDossierEditAPI(saveParams);
      console.log('✅ Saved edit to appropriate v2 (raw/consensus/alignment) and updated HEAD');
      // Keep alignment panel visible; do not reset alignment state
      try {
        document.dispatchEvent(new Event('dossiers:refresh'));
        document.dispatchEvent(new CustomEvent('dossier:refreshOne', { detail: { dossierId } }));
        // Emit a draft:saved for highlighting. For consensus, construct proper id.
        let savedDraftId = '';
        if (isConsensusSelected && consensusType === 'alignment') {
          savedDraftId = `${transcriptionId}_consensus_alignment`;
        } else if (isConsensusSelected && consensusType === 'llm') {
          savedDraftId = `${transcriptionId}_consensus_llm`;
        } else if (alignmentState.alignmentState.showHeatmap || isAlignmentId) {
          // Use the same draft number resolution as for save
          let draftNumberFromId: number | null = null;
          try {
            const m = selectedId.match(/_draft_(\d+)(?:_v[12])?$/);
            if (m) draftNumberFromId = parseInt(m[1], 10);
          } catch {}
          const oneBased = draftNumberFromId || ((typeof selectedDraft === 'number') ? (selectedDraft + 1) : 1);
          savedDraftId = `${transcriptionId}_draft_${oneBased}_v2`;
        } else if (typeof selectedDraft === 'number') {
          savedDraftId = `${transcriptionId}_v${(selectedDraft as number) + 1}_v2`;
        }
        if (savedDraftId) {
          document.dispatchEvent(new CustomEvent('draft:saved', { detail: { dossierId, transcriptionId, draftId: savedDraftId } }));
        }
      } catch {}
    } catch (e: any) {
      console.error('Failed to save edit', e);
      alert(`Failed to save edit: ${e?.message || e}`);
    }
  }, [selectedDossierId, imageProcessing.selectedResult, editableDraft.editableDraftState, alignmentState]);

  // Warn when editing raw while alignment exists (staleness indicator)
  useEffect(() => {
    const meta = imageProcessing.selectedResult?.result?.metadata || {};
    const alignmentExists = !!alignmentState.alignmentState.alignmentResult?.success;
    if (alignmentExists && !alignmentState.alignmentState.showHeatmap && typeof selectedDraft === 'number') {
      // Simple non-blocking hint; could be upgraded to a banner/toast
      console.log('⚠️ Editing raw while alignment exists: alignment results may be stale until rerun');
    }
  }, [imageProcessing.selectedResult, alignmentState.alignmentState.alignmentResult, alignmentState.alignmentState.showHeatmap, selectedDraft]);

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
    return canParseJson(originalJsonText);
  }, [getOriginalJsonTextCallback]);

  // Reset draft selection when result changes, honoring selected_draft_index and consensus selection
  useEffect(() => {
    if (imageProcessing.selectedResult) {
      const meta = imageProcessing.selectedResult?.result?.metadata;
      const idx = meta?.selected_draft_index;
      const isConsensus = !!meta?.is_consensus_selected;
      console.log('🧭 Workspace result change:', {
        hasResult: true,
        selected_draft_index: idx,
        is_consensus_selected: isConsensus,
        prevSelectedDraft: selectedDraft
      });
      setSelectedDraft(isConsensus ? 'consensus' : (typeof idx === 'number' ? idx : 0));
    }
  }, [imageProcessing.selectedResult]);

  // Ensure edited buffer does not mask version switches; reset edits on versioned selection change
  useEffect(() => {
    try {
      const versionedId = imageProcessing.selectedResult?.result?.metadata?.selected_versioned_draft_id;
      // Reset when explicit version changes or when selectedDraft changes
      if (versionedId !== undefined) {
        // Silent local reset only; do NOT call backend or show confirmation
        (editableDraft as any).resetLocalEdits?.();
      }
    } catch {}
  }, [imageProcessing.selectedResult?.result?.metadata?.selected_versioned_draft_id, selectedDraft]);

  // Reset local buffer when alignment result changes (no backend revert)
  useEffect(() => {
    if (alignmentState.alignmentState.alignmentResult) {
      (editableDraft as any).resetLocalEdits?.();
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
              processingMode={imageProcessing.processingMode}
              onProcessingModeChange={imageProcessing.setProcessingMode}
              processingQueue={imageProcessing.processingQueue}
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
            consensusSettings={imageProcessing.consensusSettings}
            onConsensusSettingsChange={imageProcessing.setConsensusSettings}
            // DOSSIER SUPPORT
            selectedDossierId={selectedDossierId}
            onDossierChange={setSelectedDossierId}
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
              onRerun={async (fresh?: boolean) => {
                if (!imageProcessing.selectedResult) return;
                // If fresh, revert alignment heads Av2->Av1 for all drafts with alignment
                if (fresh) {
                  try {
                    const dossierId = imageProcessing.selectedResult?.result?.metadata?.dossier_id;
                    const transcriptionId = imageProcessing.selectedResult?.result?.metadata?.transcription_id;
                    const ra = imageProcessing.selectedResult?.result?.metadata?.redundancy_analysis;
                    const rawCount = (ra?.individual_results || []).filter((r: any) => r?.success && !(r?.metadata?.type === 'llm_consensus')).length;
                    // Revert each alignment draft to v1 (best-effort)
                    const calls: Promise<any>[] = [];
                    for (let i = 0; i < rawCount; i++) {
                      const form = new FormData();
                      form.append('dossier_id', String(dossierId || ''));
                      form.append('transcription_id', String(transcriptionId || ''));
                      form.append('alignment_draft_index', String(i));
                      form.append('purge', 'true');
                      calls.push(fetch('http://localhost:8000/api/dossier/versions/revert-to-v1', { method: 'POST', body: form }).catch(() => null));
                    }
                    await Promise.all(calls);
                  } catch {}
                }
                // Rerun alignment
                await alignmentState.handleAlign(imageProcessing.selectedResult);
              }}
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
              const meta = res?.result?.metadata;
              const idx = meta?.selected_draft_index;
              const isConsensus = !!meta?.is_consensus_selected;
              setSelectedDraft(isConsensus ? 'consensus' : (typeof idx === 'number' ? idx : 0));
              // Do not reset alignment state here; keep panel/results visible
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
            onToggleAlignmentPanel={() => {
              const hasResults = !!alignmentState.alignmentState.alignmentResult?.success;
              if (hasResults) {
                alignmentState.setShowAlignmentPanel(!alignmentState.alignmentState.showAlignmentPanel);
              } else {
                alignmentState.handleAlign(imageProcessing.selectedResult);
              }
            }}
            isAligning={alignmentState.alignmentState.isAligning}
            onTextUpdate={(newText: string) => {
              // Persist the rebuilt text from heatmap into the editable state
              try {
                editableDraft.setEditedContent(newText);
              } catch {}
            }}
            onApplyEdit={(blockIndex: number, tokenIndex: number, newValue: string, editType?: 'alternative_selection' | 'manual_edit') => {
              // Convert editType to alternatives array format
              const alternatives = editType === 'alternative_selection' ? [newValue] : undefined;
              editableDraft.applyEdit(blockIndex, tokenIndex, newValue, alternatives);
              // Auto-save immediately as Av2 when editing inside heatmap for alignment-selected draft
              if (alignmentState.alignmentState.showHeatmap) {
                handleSaveEditedContent().catch(() => {});
              }
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
            onSetEditedContent={editableDraft.setEditedContent}
            onSaveEditedContent={handleSaveEditedContent}
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