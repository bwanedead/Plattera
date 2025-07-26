import { useState, useCallback } from 'react';
import { AlignmentState, AlignmentDraft, AlignmentResult } from '../types/imageProcessing';
import { alignDraftsAPI } from '../services/imageProcessingApi';
import { generateConsensusDrafts } from '../services/consensusApi';
import { selectFinalDraftAPI } from '../services/imageProcessingApi';
import { workspaceStateManager } from '../services/workspaceStateManager';

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

    setAlignmentState(prev => ({ ...prev, isAligning: true }));

    try {
      const redundancyAnalysis = selectedResult.result.metadata.redundancy_analysis;
      const individualResults = redundancyAnalysis.individual_results || [];
      
      const drafts: AlignmentDraft[] = individualResults
        .filter((result: any) => result.success)
        .map((result: any, index: number) => ({
          draft_id: `Draft_${index + 1}`,
          blocks: [
            {
              id: 'legal_text',
              text: result.text || ''
            }
          ]
        }));

      if (drafts.length < 2) {
        throw new Error('At least 2 successful drafts are required for alignment');
      }

      console.log('🚀 Aligning drafts:', drafts);
      const alignmentResult = await alignDraftsAPI(drafts, selectedConsensusStrategy);

      console.log('📊 Alignment result received:', alignmentResult);

      // Generate consensus drafts after successful alignment
      if (alignmentResult.success && alignmentResult.alignment_results) {
        try {
          const consensusResult = await generateConsensusDrafts(alignmentResult.alignment_results);
          if (consensusResult.success && consensusResult.enhanced_alignment_results) {
            // Update the alignment result with consensus data
            alignmentResult.alignment_results = consensusResult.enhanced_alignment_results;
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