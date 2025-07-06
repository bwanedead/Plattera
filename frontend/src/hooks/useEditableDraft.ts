import { useState, useCallback, useMemo, useEffect } from 'react';
import { EditableDraftState, EditOperation, TokenMapping, AlignmentResult } from '../types/imageProcessing';

export const useEditableDraft = (
  originalText: string,
  alignmentResult: AlignmentResult | null
) => {
  const [editableDraftState, setEditableDraftState] = useState<EditableDraftState>(() => {
    // Split text into blocks (assuming blocks are separated by double newlines)
    const blockTexts = originalText.split('\n\n');
    
    return {
      originalDraft: {
        content: originalText,
        blockTexts: blockTexts
      },
      editedDraft: {
        content: originalText,
        blockTexts: blockTexts
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false
    };
  });

  // Update original text when it changes
  useEffect(() => {
    const blockTexts = originalText.split('\n\n');
    setEditableDraftState(prevState => {
      // Only update if the original text has actually changed
      if (prevState.originalDraft.content !== originalText) {
        return {
          originalDraft: {
            content: originalText,
            blockTexts: blockTexts
          },
          editedDraft: {
            content: originalText,
            blockTexts: blockTexts
          },
          editHistory: [],
          currentHistoryIndex: -1,
          hasUnsavedChanges: false
        };
      }
      return prevState;
    });
  }, [originalText]);

  // Generate token mappings from alignment result
  const tokenMappings = useMemo(() => {
    if (!alignmentResult?.alignment_results?.blocks) return {};
    
    const mappings: Record<string, TokenMapping[]> = {};
    
    Object.entries(alignmentResult.alignment_results.blocks).forEach(([blockId, blockData]: [string, any]) => {
      const alignedSequences = blockData.aligned_sequences || [];
      if (alignedSequences.length === 0) return;
      
      // Use the first aligned sequence as the reference
      const referenceSequence = alignedSequences[0];
      const tokens = referenceSequence.tokens || [];
      const originalToAlignment = referenceSequence.original_to_alignment || [];
      
      mappings[blockId] = tokens.map((token: string, alignedIndex: number) => {
        // Find the original index for this aligned position
        const originalIndex = originalToAlignment.indexOf(alignedIndex);
        
        return {
          originalStart: originalIndex,
          originalEnd: originalIndex + token.length,
          alignedIndex,
          originalText: token, // This would be the "dirty" text with special chars
          cleanedText: token   // This is the cleaned version used in alignment
        };
      });
    });
    
    return mappings;
  }, [alignmentResult]);

  // Apply an edit to the draft
  const applyEdit = useCallback((
    blockIndex: number,
    tokenIndex: number,
    newValue: string,
    editType: 'alternative_selection' | 'manual_edit' = 'manual_edit',
    confidence?: number,
    alternatives?: string[]
  ) => {
    setEditableDraftState(prevState => {
      const editId = `edit-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
      const originalValue = prevState.editedDraft.blockTexts[blockIndex];
      
      // Create the edit operation
      const editOperation: EditOperation = {
        id: editId,
        timestamp: Date.now(),
        type: editType,
        blockIndex,
        tokenIndex,
        originalValue,
        newValue,
        confidence,
        alternatives
      };

      // Apply the edit using smart re-hydration
      const newBlockTexts = [...prevState.editedDraft.blockTexts];
      newBlockTexts[blockIndex] = applyEditToBlock(
        prevState.editedDraft.blockTexts[blockIndex],
        tokenIndex,
        newValue,
        alignmentResult,
        blockIndex
      );

      // Update history (remove any future operations if we're not at the latest)
      const newHistory = prevState.editHistory.slice(0, prevState.currentHistoryIndex + 1);
      newHistory.push(editOperation);

      return {
        ...prevState,
        editedDraft: {
          content: newBlockTexts.join('\n\n'),
          blockTexts: newBlockTexts
        },
        editHistory: newHistory,
        currentHistoryIndex: newHistory.length - 1,
        hasUnsavedChanges: true
      };
    });
  }, [alignmentResult]);

  // Undo the last edit
  const undoEdit = useCallback(() => {
    setEditableDraftState(prevState => {
      if (prevState.currentHistoryIndex < 0) return prevState;
      
      const newHistoryIndex = prevState.currentHistoryIndex - 1;
      
      // Rebuild the draft by replaying history up to the new index
      const replayedDraft = replayEditHistory(
        prevState.originalDraft,
        prevState.editHistory.slice(0, newHistoryIndex + 1),
        alignmentResult
      );
      
      return {
        ...prevState,
        editedDraft: replayedDraft,
        currentHistoryIndex: newHistoryIndex,
        hasUnsavedChanges: newHistoryIndex >= 0
      };
    });
  }, [alignmentResult]);

  // Redo the next edit
  const redoEdit = useCallback(() => {
    setEditableDraftState(prevState => {
      if (prevState.currentHistoryIndex >= prevState.editHistory.length - 1) return prevState;
      
      const newHistoryIndex = prevState.currentHistoryIndex + 1;
      
      // Rebuild the draft by replaying history up to the new index
      const replayedDraft = replayEditHistory(
        prevState.originalDraft,
        prevState.editHistory.slice(0, newHistoryIndex + 1),
        alignmentResult
      );
      
      return {
        ...prevState,
        editedDraft: replayedDraft,
        currentHistoryIndex: newHistoryIndex,
        hasUnsavedChanges: newHistoryIndex >= 0
      };
    });
  }, [alignmentResult]);

  // Reset to original draft
  const resetToOriginal = useCallback(() => {
    setEditableDraftState(prevState => ({
      ...prevState,
      editedDraft: {
        content: prevState.originalDraft.content,
        blockTexts: [...prevState.originalDraft.blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false
    }));
  }, []);

  // Save current state as the new original
  const saveAsOriginal = useCallback(() => {
    setEditableDraftState(prevState => ({
      ...prevState,
      originalDraft: {
        content: prevState.editedDraft.content,
        blockTexts: [...prevState.editedDraft.blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false
    }));
  }, []);

  return {
    editableDraftState,
    applyEdit,
    undoEdit,
    redoEdit,
    resetToOriginal,
    saveAsOriginal,
    canUndo: editableDraftState.currentHistoryIndex >= 0,
    canRedo: editableDraftState.currentHistoryIndex < editableDraftState.editHistory.length - 1,
    tokenMappings
  };
};

// Helper function to apply an edit to a specific block with special character preservation
function applyEditToBlock(
  blockText: string,
  tokenIndex: number,
  newValue: string,
  alignmentResult: AlignmentResult | null,
  blockIndex: number
): string {
  if (!alignmentResult?.alignment_results?.blocks) {
    // Fallback: simple word replacement
    const words = blockText.split(' ');
    if (tokenIndex < words.length) {
      words[tokenIndex] = newValue;
      return words.join(' ');
    }
    return blockText;
  }

  // Get the block data from alignment results
  const blockKeys = Object.keys(alignmentResult.alignment_results.blocks);
  const blockKey = blockKeys[blockIndex];
  const blockData = alignmentResult.alignment_results.blocks[blockKey];
  
  if (!blockData?.aligned_sequences?.[0]) {
    // Fallback to simple replacement
    const words = blockText.split(' ');
    if (tokenIndex < words.length) {
      words[tokenIndex] = newValue;
      return words.join(' ');
    }
    return blockText;
  }

  const referenceSequence = blockData.aligned_sequences[0];
  const tokens = referenceSequence.tokens || [];
  const originalToAlignment = referenceSequence.original_to_alignment || [];
  
  // Find the original position in the text
  if (tokenIndex >= tokens.length) return blockText;
  
  const originalIndex = originalToAlignment[tokenIndex];
  if (originalIndex === undefined) return blockText;
  
  // Use a more sophisticated approach to preserve special characters
  // This is a simplified version - in reality, we'd need more complex logic
  // to handle cases like "4°00'" -> "6°08'"
  
  const words = blockText.split(' ');
  if (originalIndex < words.length) {
    const originalWord = words[originalIndex];
    const cleanedOriginal = tokens[tokenIndex];
    
    // Try to preserve special characters by pattern matching
    const preservedWord = preserveSpecialCharacters(originalWord, cleanedOriginal, newValue);
    words[originalIndex] = preservedWord;
    return words.join(' ');
  }
  
  return blockText;
}

// Helper function to preserve special characters when applying edits
function preserveSpecialCharacters(
  originalWord: string,
  cleanedWord: string,
  newValue: string
): string {
  // Common patterns for legal documents
  const patterns = [
    // Degrees and coordinates: "4°00'" -> "6°08'"
    {
      regex: /^(\d+)°(\d+)'?$/,
      replacement: (match: RegExpMatchArray, newVal: string) => {
        const newParts = newVal.split(/\s+/);
        if (newParts.length === 2) {
          return `${newParts[0]}°${newParts[1]}'`;
        }
        return newVal;
      }
    },
    // Parentheses: "(abc)" -> "(def)"
    {
      regex: /^\(([^)]+)\)$/,
      replacement: (match: RegExpMatchArray, newVal: string) => `(${newVal})`
    },
    // Quotes: "abc" -> "def"
    {
      regex: /^"([^"]+)"$/,
      replacement: (match: RegExpMatchArray, newVal: string) => `"${newVal}"`
    },
    // Brackets: "[abc]" -> "[def]"
    {
      regex: /^\[([^\]]+)\]$/,
      replacement: (match: RegExpMatchArray, newVal: string) => `[${newVal}]`
    }
  ];

  // Try each pattern
  for (const pattern of patterns) {
    const match = originalWord.match(pattern.regex);
    if (match) {
      return pattern.replacement(match, newValue);
    }
  }

  // If no pattern matches, return the new value as-is
  return newValue;
}

// Helper function to replay edit history
function replayEditHistory(
  originalDraft: EditableDraftState['originalDraft'],
  history: EditOperation[],
  alignmentResult: AlignmentResult | null
): EditableDraftState['editedDraft'] {
  let currentBlockTexts = [...originalDraft.blockTexts];
  
  for (const operation of history) {
    currentBlockTexts[operation.blockIndex] = applyEditToBlock(
      currentBlockTexts[operation.blockIndex],
      operation.tokenIndex,
      operation.newValue,
      alignmentResult,
      operation.blockIndex
    );
  }
  
  return {
    content: currentBlockTexts.join('\n\n'),
    blockTexts: currentBlockTexts
  };
} 