import { useState, useCallback } from 'react';
import { AlignmentState, AlignmentDraft } from '../types/imageProcessing';
import { alignDraftsAPI } from '../services/imageProcessingApi';

export const useAlignmentState = () => {
  const [alignmentState, setAlignmentState] = useState<AlignmentState>({
    isAligning: false,
    alignmentResult: null,
    showHeatmap: false,
    showAlignmentPanel: false
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
      console.log('📊 Confidence results:', alignmentResult.confidence_results);
      console.log('📊 Alignment results:', alignmentResult.alignment_results);
      console.log('📊 Summary:', alignmentResult.summary);

      setAlignmentState(prev => ({
        ...prev,
        isAligning: false,
        alignmentResult,
        showAlignmentPanel: true
      }));

      if (alignmentResult.success) {
        console.log('✅ Alignment completed successfully:', alignmentResult);
      } else {
        console.error('❌ Alignment failed:', alignmentResult.error);
      }
    } catch (error) {
      console.error('💥 Error during alignment:', error);
      setAlignmentState(prev => ({
        ...prev,
        isAligning: false,
        alignmentResult: {
          success: false,
          processing_time: 0,
          summary: {
            total_positions: 0,
            total_differences: 0,
            average_confidence: 0,
            quality_assessment: 'Failed',
            high_confidence_positions: 0,
            medium_confidence_positions: 0,
            low_confidence_positions: 0
          },
          error: error instanceof Error ? error.message : 'Unknown alignment error'
        }
      }));
    }
  }, [selectedConsensusStrategy]);

  const toggleHeatmap = useCallback((show: boolean) => {
    setAlignmentState(prev => ({ ...prev, showHeatmap: show }));
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
    setAlignmentState({
      isAligning: false,
      alignmentResult: null,
      showHeatmap: false,
      showAlignmentPanel: false
    });
  }, []);

  return {
    alignmentState,
    showAlignmentTable,
    selectedConsensusStrategy,
    setSelectedConsensusStrategy,
    handleAlign,
    toggleHeatmap,
    closeAlignmentPanel,
    toggleAlignmentTable,
    resetAlignmentState,
  };
}; 