import { useState, useCallback, useMemo, useEffect } from 'react';
import { EditableDraftState, EditOperation, TokenMapping, AlignmentResult } from '../types/imageProcessing';

export const useEditableDraft = (
  originalText: string,
  alignmentResult: AlignmentResult | null
) => {
  const [editableDraftState, setEditableDraftState] = useState<EditableDraftState>(() => {
    // Extract block texts from either plain text or JSON
    const blockTexts = extractBlockTexts(originalText);
    
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
    const blockTexts = extractBlockTexts(originalText);
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
          content: reconstructContent(prevState.originalDraft.content, newBlockTexts),
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
  console.log('🔧 Applying edit:', { blockIndex, tokenIndex, newValue, blockText });
  
  // FIXED: Add null/undefined checks to prevent crashes
  if (!blockText || typeof blockText !== 'string') {
    console.error('❌ Invalid blockText:', blockText);
    return blockText || '';
  }
  
  if (!alignmentResult?.alignment_results?.blocks) {
    console.log('⚠️ No alignment results, using simple word replacement');
    // Fallback: simple word replacement
    const words = blockText.split(' ');
    if (tokenIndex < words.length) {
      words[tokenIndex] = newValue;
      const result = words.join(' ');
      console.log('✅ Simple edit result:', result);
      return result;
    }
    return blockText;
  }

  // Get the block data from alignment results
  const blockKeys = Object.keys(alignmentResult.alignment_results.blocks);
  const blockKey = blockKeys[blockIndex];
  const blockData = alignmentResult.alignment_results.blocks[blockKey];
  
  console.log('📊 Block data:', { blockKeys, blockKey, hasBlockData: !!blockData });
  
  if (!blockData?.aligned_sequences?.[0]) {
    console.log('⚠️ No aligned sequences, using simple replacement');
    // Fallback to simple replacement
    // FIXED: Add safety check here too
    if (!blockText || typeof blockText !== 'string') {
      console.error('❌ Invalid blockText at aligned sequences fallback:', blockText);
      return blockText || '';
    }
    const words = blockText.split(' ');
    if (tokenIndex < words.length) {
      words[tokenIndex] = newValue;
      const result = words.join(' ');
      console.log('✅ Fallback edit result:', result);
      return result;
    }
    return blockText;
  }

  const referenceSequence = blockData.aligned_sequences[0];
  const tokens = referenceSequence.tokens || [];
  const originalToAlignment = referenceSequence.original_to_alignment || [];
  
  console.log('🔍 Token mapping data:', { 
    tokensLength: tokens.length, 
    tokenIndex, 
    targetToken: tokens[tokenIndex],
    originalToAlignmentLength: originalToAlignment.length 
  });
  
  // Find the original position in the text
  if (tokenIndex >= tokens.length) {
    console.log('❌ Token index out of bounds');
    return blockText;
  }
  
  // FIXED: Find the original index that maps TO this tokenIndex
  // originalToAlignment[i] = j means original position i maps to alignment position j
  // We need to find i such that originalToAlignment[i] = tokenIndex
  let originalIndex = -1;
  for (let i = 0; i < originalToAlignment.length; i++) {
    if (originalToAlignment[i] === tokenIndex) {
      originalIndex = i;
      break;
    }
  }
  
  console.log('🎯 Found original index:', originalIndex);
  
  if (originalIndex === -1) {
    console.log('⚠️ Could not map token index to original position, using simple replacement');
    // Fallback to simple token index replacement
    // FIXED: Add safety check here too
    if (!blockText || typeof blockText !== 'string') {
      console.error('❌ Invalid blockText at fallback stage:', blockText);
      return blockText || '';
    }
    const words = blockText.split(' ');
    if (tokenIndex < words.length) {
      words[tokenIndex] = newValue;
      const result = words.join(' ');
      console.log('✅ Simple mapping edit result:', result);
      return result;
    }
    return blockText;
  }
  
  // Use a more sophisticated approach to preserve special characters
  // FIXED: Add additional safety checks here too
  if (!blockText || typeof blockText !== 'string') {
    console.error('❌ Invalid blockText at character preservation stage:', blockText);
    return blockText || '';
  }
  
  const words = blockText.split(' ');
  console.log('📝 Words array:', words);
  
  if (originalIndex < words.length) {
    const originalWord = words[originalIndex];
    const cleanedOriginal = tokens[tokenIndex];
    
    console.log('🔤 Character preservation:', { originalWord, cleanedOriginal, newValue });
    
    // Try to preserve special characters by pattern matching
    const preservedWord = preserveSpecialCharacters(originalWord, cleanedOriginal, newValue);
    words[originalIndex] = preservedWord;
    const result = words.join(' ');
    
    console.log('✅ Final edit result:', { preservedWord, result });
    return result;
  }
  
  console.log('❌ Original index out of bounds');
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