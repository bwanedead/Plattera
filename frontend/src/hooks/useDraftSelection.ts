import { useState, useCallback } from 'react';
import { getCurrentText, getRawText } from '../utils/textSelectionUtils';
import { isJsonResult, formatJsonAsText } from '../utils/jsonFormatter';

export const useDraftSelection = (
  selectedResult: any, 
  selectedConsensusStrategy: string,
  editedText?: string, // New parameter for edited text
  hasUnsavedChanges?: boolean // New parameter to track if there are actual edits
) => {
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>('best');

  const getCurrentTextCallback = useCallback(() => {
    // Only use edited text if there are actual unsaved changes
    // This prevents the blank screen issue when no edits have been made
    const sourceText = (editedText !== undefined && hasUnsavedChanges)
      ? editedText 
      : getCurrentText({ selectedResult, selectedDraft, selectedConsensusStrategy });

    console.log('📋 Draft Selection - Source text info:', {
      usingEditedText: editedText !== undefined && hasUnsavedChanges,
      hasUnsavedChanges,
      sourceTextLength: sourceText?.length,
      sourceTextPreview: sourceText?.substring(0, 100),
      isJson: isJsonResult(sourceText)
    });

    // Now, apply JSON formatting to the determined source text.
    // This ensures that both edited and original text are displayed correctly.
    if (isJsonResult(sourceText)) {
      const formatted = formatJsonAsText(sourceText);
      console.log('✅ Applied JSON formatting:', {
        originalLength: sourceText.length,
        formattedLength: formatted.length,
        formattedPreview: formatted.substring(0, 200)
      });
      return formatted;
    }
    
    console.log('📝 No JSON formatting applied - returning source text as-is');
    return sourceText;
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText, hasUnsavedChanges]);

  const getRawTextCallback = useCallback(() => {
    // Only use edited text if there are actual unsaved changes
    // This prevents the blank screen issue when no edits have been made
    if (editedText !== undefined && hasUnsavedChanges) {
      return editedText;
    }
    return getRawText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText, hasUnsavedChanges]);

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