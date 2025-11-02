import { useState, useCallback, useEffect, useMemo } from 'react';
import { AlignmentResult } from '../types/imageProcessing';
import { getCurrentText, getRawText } from '../utils/textSelectionUtils';
import { extractCleanText } from '../utils/jsonFormatter';
import { revertToV1API } from '../services/imageProcessingApi';

interface EditOperation {
  id: string;
  timestamp: number;
  type: 'alternative_selection' | 'manual_edit';
  blockIndex: number;
  tokenIndex: number;
  originalValue: string;
  newValue: string;
  alternatives?: string[];
}

interface EditableDraftState {
  originalDraft: {
    content: string;
    blockTexts: string[];
  };
  editedDraft: {
    content: string;
    blockTexts: string[];
  };
  editHistory: EditOperation[];
  currentHistoryIndex: number;
  hasUnsavedChanges: boolean;
  editedFromDraft: number | 'consensus' | 'best' | null;
}

interface TokenMapping {
  blockIndex: number;
  tokenIndex: number;
  originalIndex: number;
  token: string;
}

export const useEditableDraft = (
  selectedResult: any,
  alignmentResult: AlignmentResult | null,
  selectedDraft: number | 'consensus' | 'best',
  selectedConsensusStrategy: string
) => {
  // Draft context (for logging/UI; editing allowed regardless of redundancy)
  const redundancyCount = selectedResult?.result?.metadata?.redundancy_analysis?.count || 1;
  const isMultiDraft = redundancyCount > 1;
  
  // Get text using alignment tokens when available, fallback to clean text
  const originalText = useMemo(() => {
    if (!selectedResult) return '';
    
    console.log('🔄 Getting original text for:', { selectedDraft, selectedResult: !!selectedResult });
    
    // TRY: Build from alignment tokens first (for correct token mapping)
    if (alignmentResult?.success) {
      console.log('🔄 Trying to build text from alignment tokens for draft:', selectedDraft);
      
      const alignmentBlocks = alignmentResult.alignment_results?.blocks;
      if (alignmentBlocks) {
        const blockTexts: string[] = [];
        let hasValidTokens = false;
        
        Object.keys(alignmentBlocks).sort().forEach((blockId, blockIndex) => {
          const alignmentBlock = alignmentBlocks[blockId];
          
          // Find the right sequence for the selected draft
          let selectedSequence = alignmentBlock.aligned_sequences?.[0];
          
          if (typeof selectedDraft === 'number' && alignmentBlock.aligned_sequences) {
            const sequenceForDraft = alignmentBlock.aligned_sequences.find((seq: any) => {
              return seq.draft_id === `draft_${selectedDraft}` || 
                     seq.draft_id === `Draft ${selectedDraft + 1}` ||
                     seq.draft_index === selectedDraft;
            });
            
            if (sequenceForDraft) {
              selectedSequence = sequenceForDraft;
            } else if (selectedDraft < alignmentBlock.aligned_sequences.length) {
              selectedSequence = alignmentBlock.aligned_sequences[selectedDraft];
            }
          }
          
          // Extract tokens
          if (selectedSequence?.tokens) {
            const displayTokens = selectedSequence.tokens.filter((token: string) => token && token !== '-');
            if (displayTokens.length > 0) {
              const blockText = displayTokens.join(' ');
              blockTexts.push(blockText);
              hasValidTokens = true;
              
              console.log(`📝 Block ${blockIndex} from alignment:`, {
                blockId,
                tokenCount: displayTokens.length,
                firstTokens: displayTokens.slice(0, 5)
              });
            }
          }
        });
        
        if (hasValidTokens && blockTexts.length > 0) {
          const alignmentText = blockTexts.join('\n\n');
          console.log('✅ Built text from alignment tokens:', {
            totalBlocks: blockTexts.length,
            textLength: alignmentText.length,
            textPreview: alignmentText.substring(0, 200)
          });
          return alignmentText;
        }
      }
    }
    
    // FALLBACK: Use the old working method
    console.log('🔄 Falling back to clean text extraction');
    const result = selectedResult.result;
    if (!result) return '';
    
    // For redundancy analysis, get the specific draft
    const redundancyAnalysis = result.metadata?.redundancy_analysis;
    if (redundancyAnalysis && typeof selectedDraft === 'number') {
      const individualResults = (redundancyAnalysis.individual_results || []).filter((r: any) => r.success);
      if (selectedDraft < individualResults.length) {
        const draftText = individualResults[selectedDraft].text || '';
        const cleanText = extractCleanText(draftText);
        console.log('📝 Using clean draft text (fallback):', {
          selectedDraft,
          cleanTextLength: cleanText.length,
          cleanTextPreview: cleanText.substring(0, 200)
        });
        return cleanText;
      }
    }
    
    // Final fallback to main extracted text
    const fallbackText = result.extracted_text || '';
    const cleanFallback = extractCleanText(fallbackText);
    console.log('📝 Using clean fallback text:', {
      cleanTextLength: cleanFallback.length,
      cleanTextPreview: cleanFallback.substring(0, 200)
    });
    return cleanFallback;
  }, [alignmentResult, selectedResult, selectedDraft]);

  // Initialize state
  const [editableDraftState, setEditableDraftState] = useState<EditableDraftState>(() => {
    const blockTexts = extractBlockTexts(originalText);
    return {
      originalDraft: {
        content: originalText,
        blockTexts
      },
      editedDraft: {
        content: originalText,
        blockTexts: [...blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null
    };
  });

  // Reset when original text changes (new document/draft)
  useEffect(() => {
    if (originalText !== editableDraftState.originalDraft.content) {
      console.log('🔄 Resetting draft state due to text change');
      const blockTexts = extractBlockTexts(originalText);
      setEditableDraftState({
        originalDraft: {
          content: originalText,
          blockTexts
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
    }
  }, [originalText]);

  // Apply edit function
  const applyEdit = useCallback((blockIndex: number, tokenIndex: number, newValue: string, alternatives?: string[]) => {
    console.log('🎯 Applying edit:', { blockIndex, tokenIndex, newValue, selectedDraft });
    
    setEditableDraftState(prevState => {
      console.log('🚨 === CRITICAL EDIT DEBUG START ===');
      console.log('🚨 Original text analysis:', {
        originalTextLength: originalText.length,
        originalTextPreview: originalText.substring(0, 200),
        originalBlockTexts: extractBlockTexts(originalText).map((block, i) => `Block ${i}: ${block.substring(0, 50)}...`)
      });
      console.log('🚨 Current edited state:', {
        editedContent: prevState.editedDraft.content.substring(0, 200),
        editedBlockTexts: prevState.editedDraft.blockTexts.map((block, i) => `Block ${i}: ${block.substring(0, 50)}...`)
      });
      console.log('🚨 === CRITICAL EDIT DEBUG END ===');
      console.log('🚨 TEXT SOURCE COMPARISON:', {
        hookOriginalText: originalText.substring(0, 200),
        hookBlockTexts: prevState.editedDraft.blockTexts.map((block, i) => `${i}: ${block.substring(0, 50)}`),
        selectedResultText: getCurrentText({ selectedResult, selectedDraft, selectedConsensusStrategy }).substring(0, 200)
      });
      
      // INTENSIVE DEBUG: Show exact token mapping
      console.log('🔍 INTENSIVE TOKEN MAPPING DEBUG:');
      console.log('🔍 Original text split into blocks:');
      const debugBlocks = extractBlockTexts(originalText);
      debugBlocks.forEach((block, i) => {
        const words = block.split(' ');
        console.log(`🔍 Block ${i} (${words.length} words):`, words.slice(0, 10).map((w, j) => `${j}: "${w}"`));
      });
      
      console.log('🔍 Current edited blocks:');
      prevState.editedDraft.blockTexts.forEach((block, i) => {
        const words = block.split(' ');
        console.log(`🔍 Edited Block ${i} (${words.length} words):`, words.slice(0, 10).map((w, j) => `${j}: "${w}"`));
      });
      const currentBlockTexts = [...prevState.editedDraft.blockTexts];
      const targetBlock = currentBlockTexts[blockIndex];
      
      if (!targetBlock) {
        console.error('❌ Block index out of bounds:', blockIndex);
        return prevState;
      }

      const words = targetBlock.split(' ');
      console.log('📊 Token mapping debug:', {
        blockIndex,
        tokenIndex,
        newValue,
        targetBlock: targetBlock.substring(0, 100),
        totalWords: words.length,
        targetWord: words[tokenIndex],
        wordsAround: words.slice(Math.max(0, tokenIndex - 3), tokenIndex + 4).map((w, i) => `${i + Math.max(0, tokenIndex - 3)}: ${w}`),
        requestedEdit: `${words[tokenIndex]} → ${newValue}`
      });
      
      const originalWord = words[tokenIndex] || '';
      
      if (tokenIndex >= words.length) {
        console.error('❌ Token index out of bounds:', tokenIndex, 'in', words.length, 'words');
        console.error('❌ Available words:', words.slice(0, 10).map((w, i) => `${i}: ${w}`));
        return prevState;
      }

      // Apply the edit with character preservation
      const preservedValue = preserveSpecialCharacters(originalWord, originalWord, newValue);
      console.log('✏️ Applying edit:', { 
        originalWord, 
        preservedValue, 
        tokenIndex, 
        beforeEdit: words.slice(Math.max(0, tokenIndex - 2), tokenIndex + 3) 
      });
      
      words[tokenIndex] = preservedValue;
      currentBlockTexts[blockIndex] = words.join(' ');
      
      // Reconstruct the full content
      const newContent = currentBlockTexts.join('\n\n');
      
      console.log('📝 Edit result:', {
        blockIndex,
        oldBlockText: targetBlock.substring(0, 100),
        newBlockText: currentBlockTexts[blockIndex].substring(0, 100),
        afterEdit: words.slice(Math.max(0, tokenIndex - 2), tokenIndex + 3)
      });
      
      // Create edit operation
      const editOperation: EditOperation = {
        id: `edit_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        timestamp: Date.now(),
        type: alternatives ? 'alternative_selection' : 'manual_edit',
        blockIndex,
        tokenIndex,
        originalValue: originalWord,
        newValue: preservedValue,
        alternatives
      };

      // Add to history
      const newHistory = [
        ...prevState.editHistory.slice(0, prevState.currentHistoryIndex + 1),
        editOperation
      ];

      const newState = {
        ...prevState,
        editedDraft: {
          content: newContent,
          blockTexts: currentBlockTexts
        },
        editHistory: newHistory,
        currentHistoryIndex: newHistory.length - 1,
        hasUnsavedChanges: true,
        editedFromDraft: selectedDraft
      };

      console.log('✅ Edit applied successfully:', {
        editedFromDraft: newState.editedFromDraft,
        selectedDraft,
        hasUnsavedChanges: newState.hasUnsavedChanges,
        editOperation
      });

      return newState;
    });
  }, [selectedDraft, originalText]);

  // Undo edit
  const undoEdit = useCallback(() => {
    setEditableDraftState(prevState => {
      if (prevState.currentHistoryIndex < 0) return prevState;
      
      const newHistoryIndex = prevState.currentHistoryIndex - 1;
      const newEditedDraft = replayEditHistory(
        prevState.originalDraft,
        prevState.editHistory.slice(0, newHistoryIndex + 1)
      );
      
      return {
        ...prevState,
        editedDraft: newEditedDraft,
        currentHistoryIndex: newHistoryIndex,
        hasUnsavedChanges: newHistoryIndex >= 0,
        editedFromDraft: newHistoryIndex >= 0 ? prevState.editedFromDraft : null
      };
    });
  }, []);

  // Redo edit
  const redoEdit = useCallback(() => {
    setEditableDraftState(prevState => {
      if (prevState.currentHistoryIndex >= prevState.editHistory.length - 1) return prevState;
      
      const newHistoryIndex = prevState.currentHistoryIndex + 1;
      const newEditedDraft = replayEditHistory(
        prevState.originalDraft,
        prevState.editHistory.slice(0, newHistoryIndex + 1)
      );
      
      return {
        ...prevState,
        editedDraft: newEditedDraft,
        currentHistoryIndex: newHistoryIndex,
        hasUnsavedChanges: true,
        editedFromDraft: selectedDraft
      };
    });
  }, [selectedDraft]);

  // Reset to original - with backend integration and confirmation
  const resetToOriginal = useCallback(async () => {
    // Ensure a specific raw draft is selected for reset
    if (typeof selectedDraft !== 'number') {
      alert('Please select a specific raw draft to reset.');
      return;
    }
    
    console.log('🔴 RESET TO ORIGINAL BUTTON CLICKED');
    console.log('🔍 Current state:', {
      hasUnsavedChanges: editableDraftState.hasUnsavedChanges,
      editHistoryLength: editableDraftState.editHistory.length,
      editedFromDraft: editableDraftState.editedFromDraft,
      originalLength: editableDraftState.originalDraft.content.length,
      editedLength: editableDraftState.editedDraft.content.length,
      contentsMatch: editableDraftState.originalDraft.content === editableDraftState.editedDraft.content
    });

    const hasUnsavedChanges = editableDraftState.hasUnsavedChanges;
    const hasSavedEdits = editableDraftState.originalDraft.content !== editableDraftState.editedDraft.content;
    const hasAnyEdits = hasUnsavedChanges || hasSavedEdits;
    
    console.log('🔍 Edit status:', { hasUnsavedChanges, hasSavedEdits, hasAnyEdits });
    
    // ALWAYS show confirmation dialog if there are any edits (saved or unsaved)
    // This catches the case where user saved v2 in previous session
    if (hasAnyEdits) {
      console.log('⚠️ Showing confirmation dialog - edits will be lost');
      const confirmed = window.confirm(
        'Are you sure you want to reset to the original?\n\n' +
        'This will permanently delete all edits (including previously saved edits) and restore the original version.'
      );
      if (!confirmed) {
        console.log('❌ User cancelled reset');
        return;
      }
      console.log('✅ User confirmed reset');
    } else {
      console.log('ℹ️ No edits detected - proceeding without confirmation');
    }

    // Extract backend context
    const dossierId = selectedResult?.result?.metadata?.dossier_id;
    const transcriptionId = selectedResult?.result?.metadata?.transcription_id;
    
    console.log('📋 Context:', { dossierId, transcriptionId });

    // Optimistically reset frontend state
    console.log('🔄 Resetting frontend state...');
    setEditableDraftState(prevState => ({
      ...prevState,
      editedDraft: {
        content: prevState.originalDraft.content,
        blockTexts: [...prevState.originalDraft.blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null
    }));
    console.log('✅ Frontend state reset complete');

    // Call backend to revert per-draft HEAD to v1 and purge v2
    if (dossierId && transcriptionId) {
      try {
        console.log('🔄 Calling backend revert API...');
        await revertToV1API({
          dossierId: String(dossierId),
          transcriptionId: String(transcriptionId),
          purge: true, // Delete v2 files completely
          draftIndex: selectedDraft as number
        });
        console.log('✅ Backend revert successful - v2 deleted, HEAD now points to v1');
        
        // Force a re-fetch of the current draft to show v1 content
        // Instead of refreshing entire dossier (which causes scroll jump)
        console.log('🔄 Triggering focused refresh...');
        try {
          // Dispatch a custom event with the specific draft info
          const event = new CustomEvent('draft:reverted', {
            detail: { dossierId, transcriptionId }
          });
          document.dispatchEvent(event);
          console.log('✅ Draft revert event dispatched');
        } catch (e) {
          console.warn('⚠️ Could not dispatch draft revert event:', e);
        }
        
      } catch (error) {
        console.error('❌ Backend revert failed:', error);
        alert(
          `Warning: Local edits were cleared but backend revert failed.\n\n${
            error instanceof Error ? error.message : String(error)
          }\n\nYou may need to refresh the page.`
        );
      }
    } else {
      console.warn('⚠️ Missing dossier or transcription context - backend revert skipped');
    }
    
    console.log('🏁 Reset to original complete');
  }, [editableDraftState, selectedResult, isMultiDraft, redundancyCount]);

  // Reset local buffer to original silently (no confirmation, no backend)
  const resetLocalEdits = useCallback(() => {
    setEditableDraftState(prevState => ({
      ...prevState,
      editedDraft: {
        content: prevState.originalDraft.content,
        blockTexts: [...prevState.originalDraft.blockTexts]
      },
      editHistory: [],
      currentHistoryIndex: -1,
      hasUnsavedChanges: false,
      editedFromDraft: null
    }));
  }, []);

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

  // Get current text (either edited or original)
  const getCurrentDisplayText = useCallback(() => {
    console.log('🔍 getCurrentDisplayText called:', {
      hasUnsavedChanges: editableDraftState.hasUnsavedChanges,
      editedFromDraft: editableDraftState.editedFromDraft,
      selectedDraft,
      willReturnEdited: editableDraftState.hasUnsavedChanges && editableDraftState.editedFromDraft === selectedDraft
    });

    if (editableDraftState.hasUnsavedChanges && editableDraftState.editedFromDraft === selectedDraft) {
      console.log('📝 Returning edited content:', editableDraftState.editedDraft.content.substring(0, 200));
      return editableDraftState.editedDraft.content;
    }
    console.log('📄 Returning original text:', originalText.substring(0, 200));
    return originalText;
  }, [editableDraftState, selectedDraft, originalText]);

  return {
    editableDraftState,
    applyEdit,
    undoEdit,
    redoEdit,
    resetToOriginal,
    resetLocalEdits,
    saveAsOriginal,
    canUndo: editableDraftState.currentHistoryIndex >= 0,
    canRedo: editableDraftState.currentHistoryIndex < editableDraftState.editHistory.length - 1,
    getCurrentDisplayText,
    originalText, // Export for debugging
    isMultiDraft, // For UI messaging only
    redundancyCount, // For UI messaging only
    setEditedContent: (text: string) => {
      const blocks = extractBlockTexts(text);
      setEditableDraftState(prev => ({
        ...prev,
        editedDraft: { content: text, blockTexts: blocks },
        hasUnsavedChanges: true,
        editedFromDraft: selectedDraft
      }));
    }
  };
};

// Helper functions
function preserveSpecialCharacters(
  originalWord: string,
  cleanedWord: string,
  newValue: string
): string {
  if (!originalWord || !newValue) return newValue;
  
  // Pattern matching for common special characters
  const patterns = [
    { regex: /^(\d+)°(\d+)'$/, replacement: (match: RegExpMatchArray) => `${newValue}°${match[2]}'` },
    { regex: /^(\d+)°(\d+)$/, replacement: () => `${newValue}°` },
    { regex: /^\(([^)]+)\)$/, replacement: () => `(${newValue})` },
    { regex: /^"([^"]+)"$/, replacement: () => `"${newValue}"` },
    { regex: /^\[([^\]]+)\]$/, replacement: () => `[${newValue}]` },
    { regex: /^'([^']+)'$/, replacement: () => `'${newValue}'` }
  ];
  
  for (const pattern of patterns) {
    const match = originalWord.match(pattern.regex);
    if (match) {
      return pattern.replacement(match);
    }
  }
  
  return newValue;
}

function extractBlockTexts(text: string): string[] {
  if (!text) return [];
  return text.split('\n\n').filter(block => block.trim().length > 0);
}

function replayEditHistory(
  originalDraft: EditableDraftState['originalDraft'],
  history: EditOperation[]
): EditableDraftState['editedDraft'] {
  const blockTexts = [...originalDraft.blockTexts];
  
  for (const edit of history) {
    const targetBlock = blockTexts[edit.blockIndex];
    if (!targetBlock) continue;
    
    const words = targetBlock.split(' ');
    if (edit.tokenIndex >= words.length) continue;
    
    words[edit.tokenIndex] = edit.newValue;
    blockTexts[edit.blockIndex] = words.join(' ');
  }
  
  return {
    content: blockTexts.join('\n\n'),
    blockTexts
  };
}