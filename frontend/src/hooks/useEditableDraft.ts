import { useState, useCallback, useMemo } from 'react';
import { EditOperation, EditableDraftState, AlignmentResult, TokenMapping } from '../types/imageProcessing';

export const useEditableDraft = (
  originalText: string,
  alignmentResult: AlignmentResult | null,
  currentSelectedDraft?: number | 'consensus' | 'best' // Add parameter to track which draft is currently selected
) => {
  // Initialize state with proper structure
  const [editableDraftState, setEditableDraftState] = useState<EditableDraftState>(() => {
    const blockTexts = extractBlockTexts(originalText);
    return {
      originalDraft: {
        content: originalText,
        blockTexts: [...blockTexts]
      },
      editedDraft: {
        content: originalText,
        blockTexts: [...blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null // Track which draft edits were made on
    };
  });

  // Create token mappings for alignment-based editing
  const tokenMappings = useMemo(() => {
    if (!alignmentResult?.alignment_results?.blocks) return [];
    
    const mappings: TokenMapping[] = [];
    const blocks = alignmentResult.alignment_results.blocks;
    
    Object.entries(blocks).forEach(([blockKey, blockData]) => {
      if ((blockData as any)?.aligned_sequences?.[0]) {
        const sequence = (blockData as any).aligned_sequences[0];
        const tokens = sequence.tokens || [];
        const originalToAlignment = sequence.original_to_alignment || [];
        
        tokens.forEach((token: string, index: number) => {
          mappings.push({
            originalStart: index,
            originalEnd: index,
            alignedIndex: index,
            originalText: token,
            cleanedText: token
          });
        });
      }
    });
    
    return mappings;
  }, [alignmentResult]);

  // Reset state when original text changes
  const resetToOriginalText = useCallback(() => {
    const blockTexts = extractBlockTexts(originalText);
    setEditableDraftState({
      originalDraft: {
        content: originalText,
        blockTexts: [...blockTexts]
      },
      editedDraft: {
        content: originalText,
        blockTexts: [...blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null
    });
  }, [originalText]);

  // Apply edit with improved tracking and mapping
  const applyEdit = useCallback((blockIndex: number, tokenIndex: number, newValue: string, alternatives?: string[]) => {
    console.log('🎯 Applying edit:', { blockIndex, tokenIndex, newValue, currentSelectedDraft });
    
    setEditableDraftState(prevState => {
      const currentBlockTexts = [...prevState.editedDraft.blockTexts];
      const targetBlock = currentBlockTexts[blockIndex];
      
      if (!targetBlock) {
        console.error('❌ Block index out of bounds:', blockIndex);
        return prevState;
      }

      // Get the original word for better debugging
      const words = targetBlock.split(' ');
      const originalWord = words[tokenIndex] || '';
      console.log('🔍 Original word at position:', { tokenIndex, originalWord, totalWords: words.length });

      // Apply the edit with improved mapping
      const updatedBlockText = applyEditToBlock(
        targetBlock, 
        tokenIndex, 
        newValue, 
        alignmentResult,
        blockIndex
      );

      console.log('📝 Block edit result:', {
        before: targetBlock.substring(0, 100),
        after: updatedBlockText.substring(0, 100),
        changed: targetBlock !== updatedBlockText
      });

      if (updatedBlockText === targetBlock) {
        console.log('⚠️ No change applied - edit may have failed');
        return prevState;
      }

      currentBlockTexts[blockIndex] = updatedBlockText;
      
      // Reconstruct the full content
      const newContent = reconstructContent(prevState.originalDraft.content, currentBlockTexts);
      
      // Create edit operation
      const editOperation: EditOperation = {
        id: `edit_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        timestamp: Date.now(),
        type: alternatives ? 'alternative_selection' : 'manual_edit',
        blockIndex,
        tokenIndex,
        originalValue: originalWord,
        newValue,
        alternatives
      };

      // Add to history (remove any future operations if we're not at the end)
      const newHistory = [
        ...prevState.editHistory.slice(0, prevState.currentHistoryIndex + 1),
        editOperation
      ];

      return {
        ...prevState,
        editedDraft: {
          content: newContent,
          blockTexts: currentBlockTexts
        },
        editHistory: newHistory,
        currentHistoryIndex: newHistory.length - 1,
        hasUnsavedChanges: true,
        // Track which draft the edit was made on
        editedFromDraft: prevState.editedFromDraft || currentSelectedDraft || null
      };
    });
  }, [alignmentResult, currentSelectedDraft]);

  // Undo edit
  const undoEdit = useCallback(() => {
    setEditableDraftState(prevState => {
      if (prevState.currentHistoryIndex < 0) return prevState;
      
      const newHistoryIndex = prevState.currentHistoryIndex - 1;
      const newEditedDraft = replayEditHistory(
        prevState.originalDraft,
        prevState.editHistory.slice(0, newHistoryIndex + 1),
        alignmentResult
      );
      
      return {
        ...prevState,
        editedDraft: newEditedDraft,
        currentHistoryIndex: newHistoryIndex,
        hasUnsavedChanges: newHistoryIndex >= 0,
        editedFromDraft: newHistoryIndex >= 0 ? prevState.editedFromDraft : null
      };
    });
  }, [alignmentResult]);

  // Redo edit
  const redoEdit = useCallback(() => {
    setEditableDraftState(prevState => {
      if (prevState.currentHistoryIndex >= prevState.editHistory.length - 1) return prevState;
      
      const newHistoryIndex = prevState.currentHistoryIndex + 1;
      const newEditedDraft = replayEditHistory(
        prevState.originalDraft,
        prevState.editHistory.slice(0, newHistoryIndex + 1),
        alignmentResult
      );
      
      return {
        ...prevState,
        editedDraft: newEditedDraft,
        currentHistoryIndex: newHistoryIndex,
        hasUnsavedChanges: true,
        editedFromDraft: currentSelectedDraft || prevState.editedFromDraft
      };
    });
  }, [alignmentResult, currentSelectedDraft]);

  // Save current state as new original
  const saveAsOriginal = useCallback(() => {
    setEditableDraftState(prevState => ({
      originalDraft: {
        content: prevState.editedDraft.content,
        blockTexts: [...prevState.editedDraft.blockTexts]
      },
      editedDraft: {
        content: prevState.editedDraft.content,
        blockTexts: [...prevState.editedDraft.blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null
    }));
  }, []);

  // Reset to original
  const resetToOriginal = useCallback(() => {
    setEditableDraftState(prevState => ({
      ...prevState,
      editedDraft: {
        content: prevState.originalDraft.content,
        blockTexts: [...prevState.originalDraft.blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null // Reset the tracked draft
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

// IMPROVED: Helper function with better debugging and fallback approaches
function applyEditToBlock(
  blockText: string,
  tokenIndex: number,
  newValue: string,
  alignmentResult: AlignmentResult | null,
  blockIndex: number
): string {
  console.log('🔧 Applying edit to block:', { blockIndex, tokenIndex, newValue, blockTextLength: blockText?.length });
  
  // Add null/undefined checks to prevent crashes
  if (!blockText || typeof blockText !== 'string') {
    console.error('❌ Invalid blockText:', blockText);
    return blockText || '';
  }
  
  const words = blockText.split(' ');
  console.log('📊 Block analysis:', { 
    totalWords: words.length, 
    targetIndex: tokenIndex,
    targetWord: words[tokenIndex],
    wordsAroundTarget: words.slice(Math.max(0, tokenIndex - 2), tokenIndex + 3)
  });

  // APPROACH 1: Try alignment-based mapping if available
  if (alignmentResult?.alignment_results?.blocks) {
    const blockKeys = Object.keys(alignmentResult.alignment_results.blocks);
    const blockKey = blockKeys[blockIndex];
    const blockData = alignmentResult.alignment_results.blocks[blockKey];
    
    if (blockData?.aligned_sequences?.[0]) {
      const referenceSequence = blockData.aligned_sequences[0];
      const tokens = referenceSequence.tokens || [];
      const originalToAlignment = referenceSequence.original_to_alignment || [];
      
      console.log('🎯 Alignment mapping attempt:', { 
        tokensLength: tokens.length, 
        originalToAlignmentLength: originalToAlignment.length,
        targetTokenIndex: tokenIndex,
        alignedToken: tokens[tokenIndex]
      });
      
      // Try to find the original index
      let originalIndex = -1;
      
      // IMPROVED: Try multiple mapping approaches
      for (let i = 0; i < originalToAlignment.length; i++) {
        if (originalToAlignment[i] === tokenIndex) {
          originalIndex = i;
          console.log('✅ Found original index via alignment:', { originalIndex, mappedToToken: tokenIndex });
          break;
        }
      }
      
      // If alignment mapping worked, apply the edit
      if (originalIndex !== -1 && originalIndex < words.length) {
        const originalWord = words[originalIndex];
        const alignedToken = tokens[tokenIndex];
        
        console.log('🔤 Alignment-based edit:', { 
          originalIndex, 
          originalWord, 
          alignedToken, 
          newValue 
        });
        
        const preservedWord = preserveSpecialCharacters(originalWord, alignedToken, newValue);
        words[originalIndex] = preservedWord;
        const result = words.join(' ');
        
        console.log('✅ Alignment edit successful');
        return result;
      } else {
        console.log('⚠️ Alignment mapping failed, falling back to direct approach');
      }
    }
  }
  
  // APPROACH 2: Direct token index mapping (fallback)
  console.log('🔄 Using direct token mapping fallback');
  if (tokenIndex < words.length) {
    const originalWord = words[tokenIndex];
    console.log('🎯 Direct edit:', { tokenIndex, originalWord, newValue });
    
    // Use simpler preservation for direct mapping
    const preservedWord = preserveSpecialCharacters(originalWord, originalWord, newValue);
    words[tokenIndex] = preservedWord;
    const result = words.join(' ');
    
    console.log('✅ Direct edit successful');
    return result;
  }
  
  console.log('❌ All mapping approaches failed');
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
  
  // FIXED: Add validation to prevent corrupted state
  console.log('🔄 Replaying edit history:', { historyLength: history.length, blockTextsLength: currentBlockTexts.length });
  
  for (const operation of history) {
    // FIXED: Validate operation before applying
    if (!operation || operation.blockIndex < 0 || operation.blockIndex >= currentBlockTexts.length) {
      console.error('❌ Invalid operation:', operation);
      continue;
    }
    
    const currentText = currentBlockTexts[operation.blockIndex];
    if (!currentText || typeof currentText !== 'string') {
      console.error('❌ Invalid block text at index:', operation.blockIndex, currentText);
      continue;
    }
    
    try {
      const editedText = applyEditToBlock(
        currentText,
        operation.tokenIndex,
        operation.newValue,
        alignmentResult,
        operation.blockIndex
      );
      
      // FIXED: Validate the result
      if (editedText && typeof editedText === 'string') {
        currentBlockTexts[operation.blockIndex] = editedText;
      } else {
        console.error('❌ Invalid edit result:', editedText);
      }
    } catch (error) {
      console.error('❌ Error applying edit:', error);
    }
  }
  
  // FIXED: Validate final state
  const validBlockTexts = currentBlockTexts.filter(text => text && typeof text === 'string');
  if (validBlockTexts.length !== currentBlockTexts.length) {
    console.error('❌ Some block texts are invalid, using original instead');
    currentBlockTexts = [...originalDraft.blockTexts];
  }
  
  return {
    content: reconstructContent(originalDraft.content, currentBlockTexts),
    blockTexts: currentBlockTexts
  };
}

// Helper function to extract block texts from either plain text or JSON
function extractBlockTexts(text: string): string[] {
  if (!text) return [];
  
  console.log('📋 Extracting block texts from:', text.substring(0, 100) + '...');
  
  // Check if the text is JSON
  const trimmedText = text.trim();
  if (trimmedText.startsWith('{') || trimmedText.startsWith('[')) {
    try {
      const parsed = JSON.parse(text);
      
      // Handle document structure with sections
      if (parsed.sections && Array.isArray(parsed.sections)) {
                 const blockTexts = parsed.sections.map((section: any) => {
           if (section.body) {
             return section.body;
           }
           return section.header || '';
         }).filter((text: string) => text && text.trim());
        
        console.log('✅ Extracted blocks from JSON:', blockTexts.length, 'blocks');
        return blockTexts;
      }
      
      // Handle other JSON structures
      if (parsed.content && typeof parsed.content === 'string') {
        const blockTexts = parsed.content.split('\n\n');
        console.log('✅ Extracted blocks from JSON content:', blockTexts.length, 'blocks');
        return blockTexts;
      }
      
      // If it's a simple string in JSON
      if (typeof parsed === 'string') {
        const blockTexts = parsed.split('\n\n');
        console.log('✅ Extracted blocks from JSON string:', blockTexts.length, 'blocks');
        return blockTexts;
      }
    } catch (e) {
      console.log('⚠️ Failed to parse JSON, treating as plain text');
    }
  }
  
  // Fallback to plain text splitting
  const blockTexts = text.split('\n\n');
  console.log('✅ Extracted blocks from plain text:', blockTexts.length, 'blocks');
  return blockTexts;
}

// Helper function to reconstruct content from block texts
function reconstructContent(originalContent: string, blockTexts: string[]): string {
  if (!originalContent || !blockTexts?.length) return originalContent;
  
  console.log('🔧 Reconstructing content from blocks:', blockTexts.length, 'blocks');
  
  // Check if the original content is JSON
  const trimmedContent = originalContent.trim();
  if (trimmedContent.startsWith('{') || trimmedContent.startsWith('[')) {
    try {
      const parsed = JSON.parse(originalContent);
      
      // Handle document structure with sections
      if (parsed.sections && Array.isArray(parsed.sections)) {
        const updatedSections = parsed.sections.map((section: any, index: number) => {
          if (blockTexts[index]) {
            return {
              ...section,
              body: blockTexts[index]
            };
          }
          return section;
        });
        
        const reconstructed = {
          ...parsed,
          sections: updatedSections
        };
        
        console.log('✅ Reconstructed JSON content');
        return JSON.stringify(reconstructed);
      }
      
      // Handle other JSON structures
      if (parsed.content && typeof parsed.content === 'string') {
        const reconstructed = {
          ...parsed,
          content: blockTexts.join('\n\n')
        };
        console.log('✅ Reconstructed JSON with content field');
        return JSON.stringify(reconstructed);
      }
      
    } catch (e) {
      console.log('⚠️ Failed to parse JSON for reconstruction, using plain text');
    }
  }
  
  // Fallback to plain text reconstruction
  const reconstructed = blockTexts.join('\n\n');
  console.log('✅ Reconstructed plain text');
  return reconstructed;
} 