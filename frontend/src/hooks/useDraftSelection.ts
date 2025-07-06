import { useState, useCallback } from 'react';
import { getCurrentText, getRawText } from '../utils/textSelectionUtils';
import { isJsonResult, formatJsonAsText } from '../utils/jsonFormatter';

export const useDraftSelection = (
  selectedResult: any, 
  selectedConsensusStrategy: string,
  editedText?: string // New parameter for edited text
) => {
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>('best');

  const getCurrentTextCallback = useCallback(() => {
    // Determine the source text. If we have edited text, that is our source.
    // Otherwise, we get it from the original selection logic.
    const sourceText = editedText !== undefined 
      ? editedText 
      : getCurrentText({ selectedResult, selectedDraft, selectedConsensusStrategy });

    // Now, apply JSON formatting to the determined source text.
    // This ensures that both edited and original text are displayed correctly.
    if (isJsonResult(sourceText)) {
      return formatJsonAsText(sourceText);
    }
    
    return sourceText;
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText]);

  const getRawTextCallback = useCallback(() => {
    // If we have edited text, use it instead of the original.
    // The "raw" version of an edit is just its current state.
    if (editedText !== undefined) {
      return editedText;
    }
    return getRawText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText]);

  const isCurrentResultJsonCallback = useCallback(() => {
    const rawText = getRawTextCallback();
    return isJsonResult(rawText);
  }, [getRawTextCallback]);

  const resetDraftSelection = useCallback(() => {
    setSelectedDraft('best');
  }, []);

  return {
    selectedDraft,
    setSelectedDraft,
    getCurrentText: getCurrentTextCallback,
    getRawText: getRawTextCallback,
    isCurrentResultJson: isCurrentResultJsonCallback,
    resetDraftSelection,
  };
}; 