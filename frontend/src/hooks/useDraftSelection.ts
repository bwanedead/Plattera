import { useState, useCallback } from 'react';
import { getCurrentText, getRawText } from '../utils/textSelectionUtils';
import { isJsonResult } from '../utils/jsonFormatter';

export const useDraftSelection = (selectedResult: any, selectedConsensusStrategy: string) => {
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>('best');

  const getCurrentTextCallback = useCallback(() => {
    return getCurrentText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy]);

  const getRawTextCallback = useCallback(() => {
    return getRawText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy]);

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