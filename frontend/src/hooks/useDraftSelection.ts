import { useState, useCallback } from 'react';
import { getCurrentText, getRawText } from '../utils/textSelectionUtils';
import { isJsonResult } from '../utils/jsonFormatter';

export const useDraftSelection = (
  selectedResult: any, 
  selectedConsensusStrategy: string,
  editedText?: string // New parameter for edited text
) => {
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>('best');

  const getCurrentTextCallback = useCallback(() => {
    // If we have edited text, use it instead of the original
    if (editedText) {
      return editedText;
    }
    return getCurrentText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText]);

  const getRawTextCallback = useCallback(() => {
    // If we have edited text, use it instead of the original
    if (editedText) {
      return editedText;
    }
    return getRawText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText]);

  const isCurrentResultJson = useCallback(() => {
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
    isCurrentResultJson,
    resetDraftSelection,
  };
}; 