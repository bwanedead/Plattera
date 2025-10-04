import { useState, useCallback } from 'react';
import { AlignmentState, AlignmentDraft, AlignmentResult } from '../types/imageProcessing';
import { alignDraftsAPI, alignDraftsByIdsAPI } from '../services/imageProcessingApi';
import { generateConsensusDrafts } from '../services/consensusApi';
import { selectFinalDraftAPI } from '../services/imageProcessingApi';
import { workspaceStateManager } from '../services/workspaceStateManager';
import { textApi } from '../services/textApi';

// Frontend no longer persists alignment consensus; backend handles saving.

export const useAlignmentState = () => {
  const [alignmentState, setAlignmentState] = useState<AlignmentState>({
    isAligning: false,
    alignmentResult: null,
    showHeatmap: false,
    showAlignmentPanel: false,
    isSuggestionPopupEnabled: true // On by default
  });
  const [showAlignmentTable, setShowAlignmentTable] = useState(false);
  const [selectedConsensusStrategy, setSelectedConsensusStrategy] = useState<string>('highest_confidence');

  const handleAlign = useCallback(async (selectedResult: any) => {
    if (!selectedResult || !selectedResult.result?.metadata?.redundancy_analysis) {
      console.warn('No redundancy analysis available for alignment');
      return;
    }

    try {
      const redundancyAnalysis = selectedResult.result.metadata.redundancy_analysis;
      const individualResults = redundancyAnalysis.individual_results || [];
      const transcriptionId = selectedResult?.result?.metadata?.transcription_id;
      const dossierId = selectedResult?.result?.metadata?.dossier_id;
      
      // Filter out consensus entries
      const rawDraftResults = individualResults
        .filter((result: any) => result.success)
        .filter((result: any) => {
          const isConsensusId = typeof result?.imported_draft_id === 'string' && result.imported_draft_id.endsWith('_consensus_llm');
          const isConsensusType = (result?.metadata && result.metadata.type === 'llm_consensus') || false;
          return !(isConsensusId || isConsensusType);
        });

      if (rawDraftResults.length < 2) {
        console.warn('At least 2 successful drafts are required for alignment');
        return;
      }

      setAlignmentState(prev => ({ ...prev, isAligning: true }));

      // Prefer backend-driven alignment when dossier/transcription context is available
      let alignmentResult;
      if (transcriptionId && dossierId) {
        try {
          const draftIndices = rawDraftResults.map((_: any, i: number) => i + 1);
          alignmentResult = await alignDraftsByIdsAPI({
            dossierId,
            transcriptionId,
            draftIndices,
            versionPolicy: 'prefer_v2_else_v1',
            excludeAlignmentVersions: true
          });
        } catch (e) {
          console.warn('⚠️ Backend-driven alignment failed, falling back to client-built payload:', e);
        }
      }

      // Fallback: build minimal client-side payload only if backend path failed or no context
      if (!alignmentResult) {
        console.log('🔄 Building client-side drafts (no backend context)...');
        const draftsAll = await Promise.all(
          rawDraftResults.map(async (_r: any, index: number) => ({
            draft_id: `Draft_${index + 1}`,
            blocks: [{ id: 'legal_text', text: String(_r?.text || '') }]
          }))
        );
        const drafts = draftsAll.filter(d => (d?.blocks?.[0]?.text || '').trim().length > 0);
        if (drafts.length < 2) {
          console.warn('⚠️ Alignment aborted: need at least 2 non-empty drafts');
          setAlignmentState(prev => ({ ...prev, isAligning: false }));
          return;
        }
        alignmentResult = await alignDraftsAPI(
          drafts,
          selectedConsensusStrategy,
          { transcriptionId, dossierId, consensusDraftId: transcriptionId ? `${transcriptionId}_consensus_alignment` : undefined }
        );
      }

      console.log('📊 Alignment result received:', alignmentResult);

      // Generate consensus drafts after successful alignment
      if (alignmentResult.success && alignmentResult.alignment_results) {
        try {
          const consensusResult = await generateConsensusDrafts(alignmentResult.alignment_results);
          if (consensusResult.success && consensusResult.enhanced_alignment_results) {
            // Update the alignment result with consensus data
            alignmentResult.alignment_results = consensusResult.enhanced_alignment_results;

            // Backend now persists consensus; no frontend save needed
          }
        } catch (error) {
          console.warn('Failed to generate consensus drafts:', error);
          // Continue with original alignment result if consensus fails
        }
      }

      setAlignmentState(prev => ({
        ...prev,
        isAligning: false,
        alignmentResult,
        showAlignmentPanel: true
      }));

      // Save alignment state for persistence across page navigation
      workspaceStateManager.setImageProcessingState({
        alignmentResult,
        showAlignmentPanel: true,
        showHeatmap: false
      });

      // NEW: Automatically select consensus draft for text-to-schema
      if (alignmentResult.success) {
        try {
          console.log('🎯 Auto-selecting consensus draft for text-to-schema');
          const finalDraftResult = await selectFinalDraftAPI(
            redundancyAnalysis,
            'consensus', // Always select consensus by default
            alignmentResult
          );

          if (finalDraftResult.success) {
            console.log('✅ Auto-selected consensus draft:', {
              finalTextLength: finalDraftResult.final_text?.length,
              selectionMethod: finalDraftResult.selection_method
            });
            
            // Sync with text-to-schema workspace
            workspaceStateManager.syncFinalDraft(
              finalDraftResult.final_text, 
              finalDraftResult.metadata
            );
          } else {
            console.warn('⚠️ Failed to auto-select consensus draft:', finalDraftResult.error);
          }
        } catch (error) {
          console.warn('⚠️ Error auto-selecting consensus draft:', error);
          // Don't fail the alignment if auto-selection fails
        }
      }

    } catch (error) {
      console.error('💥 Error during alignment:', error);
      
      const errorResult: AlignmentResult = {
        success: false,
        processing_time: 0,
        summary: {
          total_positions_analyzed: 0,
          total_differences_found: 0,
          average_confidence_score: 0,
          quality_assessment: 'Failed',
          confidence_distribution: { high: 0, medium: 0, low: 0 }
        },
        error: error instanceof Error ? error.message : 'Unknown alignment error'
      };

      setAlignmentState(prev => ({
        ...prev,
        isAligning: false,
        alignmentResult: errorResult,
      }));
    }
  }, [selectedConsensusStrategy]);

  const toggleHeatmap = useCallback((show: boolean) => {
    setAlignmentState(prev => ({ ...prev, showHeatmap: show }));
  }, []);

  const toggleSuggestionPopup = useCallback((enabled: boolean) => {
    setAlignmentState(prev => ({ ...prev, isSuggestionPopupEnabled: enabled }));
  }, []);

  const closeAlignmentPanel = useCallback(() => {
    setAlignmentState(prev => ({
      ...prev,
      showAlignmentPanel: false,
      showHeatmap: false
    }));
  }, []);

  const toggleAlignmentTable = useCallback((show: boolean) => {
    setShowAlignmentTable(show);
  }, []);

  const resetAlignmentState = useCallback(() => {
    setAlignmentState(prev => ({
      isAligning: false,
      alignmentResult: null,
      showHeatmap: false,
      showAlignmentPanel: false,
      isSuggestionPopupEnabled: prev.isSuggestionPopupEnabled
    }));
  }, []);

  return {
    alignmentState,
    showAlignmentTable,
    selectedConsensusStrategy,
    setSelectedConsensusStrategy,
    handleAlign,
    toggleHeatmap,
    toggleSuggestionPopup,
    closeAlignmentPanel,
    toggleAlignmentTable,
    resetAlignmentState,
  };
}; 