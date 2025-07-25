import React, { useState } from 'react';
import { AnimatedBorder } from '../AnimatedBorder';
import { selectFinalDraftAPI } from '../../services/imageProcessingApi';

interface FinalDraftSelectorProps {
  redundancyAnalysis?: {
    individual_results: Array<{
      success: boolean;
      text: string;
      tokens: number;
      error?: string;
    }>;
    consensus_text: string;
    best_formatted_text: string;
    best_result_index: number;
    word_confidence_map?: Record<string, number>;
  };
  alignmentResult?: any;
  selectedDraft: number | 'consensus' | 'best';
  onFinalDraftSelected?: (finalText: string, metadata: any) => void;
  isProcessing?: boolean;
}

export const FinalDraftSelector: React.FC<FinalDraftSelectorProps> = ({
  redundancyAnalysis,
  alignmentResult,
  selectedDraft,
  onFinalDraftSelected,
  isProcessing = false
}) => {
  const [isHovered, setIsHovered] = useState(false);
  const [isSelecting, setIsSelecting] = useState(false);
  const [hasFinalDraft, setHasFinalDraft] = useState(false);

  // Don't show if no redundancy analysis or no alignment result
  if (!redundancyAnalysis || !alignmentResult?.success) {
    return null;
  }

  const handleSelectFinalDraft = async () => {
    if (isSelecting || isProcessing) return;

    setIsSelecting(true);
    try {
      console.log('🎯 Selecting final draft:', {
        selectedDraft,
        hasAlignmentResult: !!alignmentResult,
        redundancyAnalysis: !!redundancyAnalysis
      });

      const result = await selectFinalDraftAPI(
        redundancyAnalysis,
        selectedDraft,
        alignmentResult
      );

      if (result.success) {
        setHasFinalDraft(true);
        onFinalDraftSelected?.(result.final_text, result.metadata);
        
        // Show success feedback
        console.log('✅ Final draft selected successfully:', {
          finalText: result.final_text?.substring(0, 100) + '...',
          metadata: result.metadata
        });
      } else {
        console.error('❌ Failed to select final draft:', result.error);
        // Could add toast notification here
      }
    } catch (error) {
      console.error('❌ Error selecting final draft:', error);
      // Could add toast notification here
    } finally {
      setIsSelecting(false);
    }
  };

  const getCurrentDraftLabel = () => {
    if (selectedDraft === 'consensus') return 'Consensus Draft ��';
    if (selectedDraft === 'best') return `Draft ${redundancyAnalysis.best_result_index + 1} ⭐`;
    return `Draft ${selectedDraft + 1}`;
  };

  return (
    <div className="final-draft-selector">
      <AnimatedBorder
        isHovered={isHovered}
        borderRadius={6}
        strokeWidth={2}
      >
        <button
          className={`final-draft-button ${hasFinalDraft ? 'selected' : ''} ${isSelecting ? 'processing' : ''}`}
          onClick={handleSelectFinalDraft}
          disabled={isSelecting || isProcessing}
          onMouseEnter={() => setIsHovered(true)}
          onMouseLeave={() => setIsHovered(false)}
          title={hasFinalDraft 
            ? `Final draft selected: ${getCurrentDraftLabel()}` 
            : `Select ${getCurrentDraftLabel()} as final draft`
          }
        >
          {isSelecting ? (
            <span className="loading-spinner">⏳</span>
          ) : hasFinalDraft ? (
            <span className="final-draft-icon">✅</span>
          ) : (
            <span className="final-draft-icon">🎯</span>
          )}
          <span className="final-draft-label">
            {hasFinalDraft ? 'Final Selected' : 'Select Final'}
          </span>
        </button>
      </AnimatedBorder>
    </div>
  );
}; 