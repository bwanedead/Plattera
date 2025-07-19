import { useState, useCallback } from 'react';
import { AlignmentState, AlignmentDraft, AlignmentResult } from '../types/imageProcessing';
import { alignDraftsAPI } from '../services/alignmentApi';

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

      setAlignmentState(prev => ({
        ...prev,
        isAligning: false,
        alignmentResult,
        showAlignmentPanel: true
      }));

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