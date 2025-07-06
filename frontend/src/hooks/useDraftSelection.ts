import { useState, useCallback } from 'react';
import { getCurrentText, getRawText } from '../utils/textSelectionUtils';
import { isJsonResult, formatJsonAsText } from '../utils/jsonFormatter';

export const useDraftSelection = (
  selectedResult: any, 
  selectedConsensusStrategy: string,
  editedText?: string, // New parameter for edited text
  hasUnsavedChanges?: boolean, // New parameter to track if there are actual edits
  editedFromDraft?: number | 'consensus' | 'best' | null // Track which draft was edited
) => {
  // Default to first draft (index 0) instead of 'best'
  const [selectedDraft, setSelectedDraft] = useState<number | 'consensus' | 'best'>(0);

  const getCurrentTextCallback = useCallback(() => {
    // Only use edited text if:
    // 1. There are actual unsaved changes
    // 2. We're viewing the same draft that was edited
    const shouldUseEditedText = (
      editedText !== undefined && 
      hasUnsavedChanges && 
      editedFromDraft === selectedDraft
    );
    
    const sourceText = shouldUseEditedText
      ? editedText 
      : getCurrentText({ selectedResult, selectedDraft, selectedConsensusStrategy });

    console.log('📋 Draft Selection - Source text info:', {
      selectedDraft,
      editedFromDraft,
      shouldUseEditedText,
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
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText, hasUnsavedChanges, editedFromDraft]);

  const getRawTextCallback = useCallback(() => {
    // Only use edited text if:
    // 1. There are actual unsaved changes
    // 2. We're viewing the same draft that was edited
    const shouldUseEditedText = (
      editedText !== undefined && 
      hasUnsavedChanges && 
      editedFromDraft === selectedDraft
    );
    
    if (shouldUseEditedText) {
      return editedText;
    }
    return getRawText({ selectedResult, selectedDraft, selectedConsensusStrategy });
  }, [selectedResult, selectedDraft, selectedConsensusStrategy, editedText, hasUnsavedChanges, editedFromDraft]);

  const isCurrentResultJsonCallback = useCallback(() => {
    const rawText = getRawTextCallback();
    return isJsonResult(rawText);
  }, [getRawTextCallback]);

  const resetDraftSelection = useCallback(() => {
    setSelectedDraft(0); // Reset to first draft instead of 'best'
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