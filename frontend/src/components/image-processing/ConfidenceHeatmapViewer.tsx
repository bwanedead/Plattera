import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { AlignmentResult } from '../../types/imageProcessing';
import { extractCleanText } from '../../utils/jsonFormatter';

interface WordAlternative {
  word: string;
  source: string; // e.g., "Draft 1", "Consensus"
}

interface ConfidenceHeatmapViewerProps {
  alignmentResult: AlignmentResult;
  onTextUpdate: (newText: string) => void;
  // New editing-related props
  onApplyEdit?: (blockIndex: number, tokenIndex: number, newValue: string, editType?: 'alternative_selection' | 'manual_edit') => void;
  editableDraftState?: {
    hasUnsavedChanges: boolean;
    canUndo: boolean;
    canRedo: boolean;
    editedDraft: {
      content: string;
      blockTexts: string[];
    };
    editHistory?: any[]; // Allow any edit history format
    editedFromDraft?: number | 'consensus' | 'best' | null;
  };
  onUndoEdit?: () => void;
  onRedoEdit?: () => void;
  onResetToOriginal?: () => void;
  // New props for draft selection
  selectedDraft?: number | 'consensus' | 'best';
  redundancyAnalysis?: any;
}

interface WordData {
  word: string;
  confidence: number;
  alternatives: WordAlternative[];
  isEditable: boolean;
  isEditing: boolean;
  isHumanConfirmed: boolean;
  hasBeenEdited: boolean; // Added for tracking edited words
}

export const ConfidenceHeatmapViewer: React.FC<ConfidenceHeatmapViewerProps> = ({
  alignmentResult,
  onTextUpdate,
  onApplyEdit,
  editableDraftState,
  onUndoEdit,
  onRedoEdit,
  onResetToOriginal,
  selectedDraft,
  redundancyAnalysis
}) => {
  const [editingWordIndex, setEditingWordIndex] = useState<{ block: number, word: number } | null>(null);
  const [editingValue, setEditingValue] = useState<string>('');
  const [humanConfirmedWords, setHumanConfirmedWords] = useState<Set<string>>(new Set()); // Use "block_word" key
  const [activePopup, setActivePopup] = useState<{ block: number, word: number } | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const hidePopupTimer = useRef<NodeJS.Timeout | null>(null);

  // This is now an array of arrays, one for each block
  const blocksOfWordData = useMemo<WordData[][]>(() => {
    if (!alignmentResult?.success) return [];

    const alignmentBlocks = alignmentResult.alignment_results?.blocks;
    const confidenceBlocks = alignmentResult.confidence_results?.block_confidences;

    if (!alignmentBlocks || !confidenceBlocks) return [];

    console.log('🎯 Heatmap Data Sources:', {
      selectedDraft,
      hasRedundancyAnalysis: !!redundancyAnalysis,
      hasEditState: !!editableDraftState,
      hasUnsavedChanges: editableDraftState?.hasUnsavedChanges,
      editedFromDraft: editableDraftState?.editedFromDraft,
      editHistoryLength: editableDraftState?.editHistory?.length || 0
    });

    const processedBlocks = Object.keys(alignmentBlocks).sort().map((blockId, blockIndex) => {
      const alignmentBlock = alignmentBlocks[blockId];
      const confidenceBlock = confidenceBlocks[blockId];
      
      if (!alignmentBlock || !confidenceBlock || !confidenceBlock.scores) return [];

      // === COMPREHENSIVE HEATMAP MEMORY DEBUGGING ===
      console.log(`🔍 === HEATMAP MEMORY DEBUG BLOCK ${blockIndex} ===`);
      
      // Log complete editableDraftState
      console.log('🔍 Complete editableDraftState:', {
        exists: !!editableDraftState,
        hasUnsavedChanges: editableDraftState?.hasUnsavedChanges,
        editedFromDraft: editableDraftState?.editedFromDraft,
        editedFromDraftType: typeof editableDraftState?.editedFromDraft,
        selectedDraft: selectedDraft,
        selectedDraftType: typeof selectedDraft,
        editHistoryLength: editableDraftState?.editHistory?.length || 0,
        hasEditedDraft: !!editableDraftState?.editedDraft,
        hasBlockTexts: !!editableDraftState?.editedDraft?.blockTexts,
        blockTextsLength: editableDraftState?.editedDraft?.blockTexts?.length || 0,
        currentBlockExists: !!editableDraftState?.editedDraft?.blockTexts?.[blockIndex]
      });
      
      // Break down shouldUseEditedText condition step by step
      const condition1 = editableDraftState?.hasUnsavedChanges;
      const condition2 = !!editableDraftState?.editedDraft?.blockTexts?.[blockIndex];
      const condition3 = editableDraftState?.editedFromDraft === selectedDraft;
      
      console.log('🔍 shouldUseEditedText condition breakdown:', {
        condition1_hasUnsavedChanges: condition1,
        condition2_blockTextExists: condition2,
        condition3_editedFromDraftMatches: condition3,
        condition3_comparison: {
          editedFromDraft: editableDraftState?.editedFromDraft,
          selectedDraft: selectedDraft,
          areEqual: editableDraftState?.editedFromDraft === selectedDraft,
          strictEqual: editableDraftState?.editedFromDraft === selectedDraft
        }
      });

      const shouldUseEditedText = condition1 && condition2 && condition3;
      console.log('🔍 Final shouldUseEditedText result:', shouldUseEditedText);

      // Show edit history for this block
      if (editableDraftState?.editHistory) {
        const relevantEdits = editableDraftState.editHistory.filter((edit: any) => 
          edit.blockIndex === blockIndex
        );
        
        // ENHANCED DEBUGGING: Show actual values instead of objects
        console.log(`🔍 DETAILED EDIT HISTORY DEBUG FOR BLOCK ${blockIndex}:`);
        console.log(`🔍 Total edits in history: ${editableDraftState.editHistory.length}`);
        console.log(`🔍 Current block index being checked: ${blockIndex} (type: ${typeof blockIndex})`);
        
        editableDraftState.editHistory.forEach((edit: any, index: number) => {
          console.log(`🔍 Edit ${index}:`, {
            blockIndex: edit.blockIndex,
            blockIndexType: typeof edit.blockIndex,
            tokenIndex: edit.tokenIndex,
            originalValue: edit.originalValue,
            newValue: edit.newValue,
            matchesCurrentBlock: edit.blockIndex === blockIndex,
            strictComparison: `${edit.blockIndex} === ${blockIndex} = ${edit.blockIndex === blockIndex}`
          });
        });
        
        console.log(`🔍 Relevant edits found: ${relevantEdits.length}`);
        
        if (relevantEdits.length === 0 && editableDraftState.editHistory.length > 0) {
          console.log(`❌ MISMATCH: We have ${editableDraftState.editHistory.length} total edits but 0 match block ${blockIndex}`);
          console.log(`❌ All edit blockIndexes:`, editableDraftState.editHistory.map(e => `${e.blockIndex} (${typeof e.blockIndex})`));
        }
      } else {
        console.log(`🔍 No edit history available for block ${blockIndex}`);
      }

      let displayTokens: string[];
      
      // ALWAYS start with the original alignment tokens to preserve structure
      let selectedSequence = alignmentBlock.aligned_sequences?.[0]; // Default to first
      
      if (typeof selectedDraft === 'number' && alignmentBlock.aligned_sequences) {
        // Try to find the sequence that corresponds to the selected draft
        const sequenceForDraft = alignmentBlock.aligned_sequences.find((seq: any) => {
          return seq.draft_id === `draft_${selectedDraft}` || 
                 seq.draft_id === `Draft ${selectedDraft + 1}` ||
                 seq.draft_index === selectedDraft;
        });
        
        if (sequenceForDraft) {
          selectedSequence = sequenceForDraft;
          console.log(`🎯 Found sequence for draft ${selectedDraft}:`, selectedSequence.draft_id);
        } else if (selectedDraft < alignmentBlock.aligned_sequences.length) {
          selectedSequence = alignmentBlock.aligned_sequences[selectedDraft];
          console.log(`🎯 Using sequence at index ${selectedDraft}`);
        }
      }
      
      // Extract clean tokens from the selected sequence
      if (selectedSequence?.tokens) {
        displayTokens = selectedSequence.tokens.filter((token: string) => token && token !== '-');
        console.log(`📝 Original alignment tokens for block ${blockIndex}:`, {
          allTokens: selectedSequence.tokens,
          filteredTokens: displayTokens,
          tokenCount: displayTokens.length,
          formattingApplied: selectedSequence.formatting_applied || false
        });
        
        // Log when formatted tokens are being used
        if (selectedSequence.formatting_applied) {
          console.log(`🎨 FORMATTED TOKENS ACTIVE ► Block ${blockIndex} using formatted text with original symbols`);
        }
      } else {
        displayTokens = [];
        console.warn(`❌ No tokens found for block ${blockIndex}`);
      }
      
      // If we have edited text, apply the edits to the display tokens
      if (shouldUseEditedText && editableDraftState?.editHistory) {
        console.log(`🔍 Attempting to apply edits to block ${blockIndex}...`);
        
        const relevantEdits = editableDraftState.editHistory.filter((edit: any) => 
          edit.blockIndex === blockIndex
        );
        
        console.log(`🔍 Found ${relevantEdits.length} relevant edits for block ${blockIndex}`);
        
        if (relevantEdits.length > 0) {
          // Apply edits to the display tokens
          const originalTokens = [...displayTokens];
          const editedTokens = [...displayTokens];
          
          console.log(`🔍 Before applying edits:`, {
            originalTokens: originalTokens,
            aboutToApplyEdits: relevantEdits.map((e: any) => `Token ${e.tokenIndex}: ${e.originalValue} → ${e.newValue}`)
          });
          
          relevantEdits.forEach((edit: any, editIndex: number) => {
            console.log(`🔍 Applying edit ${editIndex + 1}/${relevantEdits.length}:`, {
              tokenIndex: edit.tokenIndex,
              originalValue: edit.originalValue,
              newValue: edit.newValue,
              tokenExists: edit.tokenIndex < editedTokens.length,
              currentTokenAtIndex: editedTokens[edit.tokenIndex]
            });
            
            if (edit.tokenIndex < editedTokens.length) {
              editedTokens[edit.tokenIndex] = edit.newValue;
              console.log(`✅ Applied edit: Token ${edit.tokenIndex} changed from "${originalTokens[edit.tokenIndex]}" to "${edit.newValue}"`);
            } else {
              console.log(`❌ Failed to apply edit: Token index ${edit.tokenIndex} out of bounds (max: ${editedTokens.length - 1})`);
            }
          });
          
          displayTokens = editedTokens;
          
          console.log(`✏️ Successfully applied ${relevantEdits.length} edits to block ${blockIndex}:`, {
            originalTokens: originalTokens,
            editedTokens: displayTokens,
            changes: relevantEdits.map((e: any) => `${e.tokenIndex}: ${originalTokens[e.tokenIndex]} → ${displayTokens[e.tokenIndex]}`)
          });
        } else {
          console.log(`🔍 No relevant edits found for block ${blockIndex}`);
        }
      } else {
        console.log(`🔍 Skipping edit application for block ${blockIndex}:`, {
          shouldUseEditedText,
          hasEditHistory: !!editableDraftState?.editHistory,
          reason: !shouldUseEditedText ? 'shouldUseEditedText is false' : 'no edit history'
        });
      }
      
      console.log(`🔍 Final display tokens for block ${blockIndex}:`, displayTokens);
      console.log(`🔍 === END HEATMAP MEMORY DEBUG BLOCK ${blockIndex} ===`);

      // Create word data objects
      return displayTokens.map((token: string, index: number) => {
        const confidence = confidenceBlock.scores[index] ?? 0.9; // Default to high confidence if missing
        const wordKey = `${blockId}_${index}`;
        
        // Check if this word has been edited
        const hasBeenEdited = editableDraftState?.editHistory?.some((edit: any) => 
          edit.blockIndex === blockIndex && edit.tokenIndex === index
        ) || false;
        
        // Build alternatives from all sequences in this block
        const alternatives: WordAlternative[] = [];
        const seenWords = new Set<string>([token.toLowerCase()]);

        alignmentBlock.aligned_sequences?.forEach((seq: any, seqIndex: number) => {
          const altToken = seq.tokens?.[index];
          if (altToken && altToken !== '-' && !seenWords.has(altToken.toLowerCase())) {
            alternatives.push({ 
              word: altToken, 
              source: seq.draft_id || `Draft ${seqIndex + 1}` 
            });
            seenWords.add(altToken.toLowerCase());
          }
        });

        return {
          word: token,
          confidence,
          alternatives,
          isEditable: false,
          isEditing: editingWordIndex?.block === blockIndex && editingWordIndex?.word === index,
          isHumanConfirmed: humanConfirmedWords.has(wordKey),
          hasBeenEdited,
        };
      });
    });
    
    return processedBlocks.filter(block => block && block.length > 0);

  }, [alignmentResult, editingWordIndex, humanConfirmedWords, editableDraftState, selectedDraft]);


  const getConfidenceColor = useCallback((confidence: number, isHumanConfirmed: boolean, hasBeenEdited: boolean) => {
    if (hasBeenEdited) {
      return 'rgba(59, 130, 246, 0.3)'; // Blue background for edited words
    }
    
    if (isHumanConfirmed) {
      return 'rgba(16, 185, 129, 0.25)'; // Emerald green for human-confirmed
    }
    
    if (confidence >= 0.8) {
      return 'rgba(34, 197, 94, 0.2)'; // Standard green for high confidence
    } else if (confidence >= 0.5) {
      return 'rgba(255, 193, 7, 0.25)'; // Standard amber for medium confidence
    } else {
      return 'rgba(220, 53, 69, 0.3)'; // Standard red for low confidence
    }
  }, []);

  const handleWordHover = (blockIndex: number, wordIndex: number, event: React.MouseEvent) => {
    const wordInfo = blocksOfWordData[blockIndex]?.[wordIndex];
    // FIXED: Allow editing on ALL words, not just contested/low-confidence ones
    if (wordInfo && !wordInfo.isHumanConfirmed) {
      // Only clear the timer if we are about to show a new popup
      if (hidePopupTimer.current) {
        clearTimeout(hidePopupTimer.current);
      }
      const rect = (event.target as HTMLElement).getBoundingClientRect();
      setPopupPosition({
        x: rect.left + rect.width / 2,
        y: rect.bottom + 5 // Position below the word now
      });
      setActivePopup({ block: blockIndex, word: wordIndex });
    }
  };

  const handleWordLeave = () => {
    hidePopupTimer.current = setTimeout(() => {
      setActivePopup(null);
    }, 200);
  };

  const handlePopupEnter = () => {
    if (hidePopupTimer.current) {
      clearTimeout(hidePopupTimer.current);
    }
  };

  const handlePopupLeave = () => {
    setActivePopup(null);
  };

  const handleSelectAlternative = (blockIndex: number, wordIndex: number, newWord: string) => {
    // CRYSTAL CLEAR DEBUGGING
    console.log('🎯 =================');
    console.log('🎯 HEATMAP CLICK DEBUG');
    console.log('🎯 =================');
    console.log('🎯 Clicked word:', blocksOfWordData[blockIndex]?.[wordIndex]?.word);
    console.log('🎯 Block index:', blockIndex);
    console.log('🎯 Word index:', wordIndex);
    console.log('🎯 New value:', newWord);
    console.log('🎯 Selected draft:', selectedDraft);
    
    // Show all words in this block with their indices
    console.log('🎯 ALL WORDS IN BLOCK', blockIndex + ':');
    blocksOfWordData[blockIndex]?.forEach((word, i) => {
      const marker = i === wordIndex ? ' <<< CLICKED' : '';
      console.log(`🎯   ${i}: "${word.word}"${marker}`);
    });
    
    console.log('🎯 =================');

    // Use the new editing system if available
    if (onApplyEdit) {
      console.log('🎯 Calling onApplyEdit with block:', blockIndex, 'wordIndex:', wordIndex, 'newWord:', newWord);
      onApplyEdit(blockIndex, wordIndex, newWord, 'alternative_selection');
    } else {
      // Fallback to old system for backward compatibility
      const newBlocksOfWordData = blocksOfWordData.map((block, bIndex) => {
        if (bIndex === blockIndex) {
          const newWords = [...block.map(w => w.word)];
          newWords[wordIndex] = newWord;
          return newWords;
        }
        return block.map(w => w.word);
      });

      const newText = newBlocksOfWordData.map(block => block.join(' ')).join('\n\n');
      onTextUpdate(newText);
    }

    // Mark this word as confirmed
    const blockId = Object.keys(alignmentResult.alignment_results!.blocks)[blockIndex];
    const originalWordIndex = blocksOfWordData[blockIndex][wordIndex].isEditing ? editingWordIndex!.word : wordIndex;
    const wordKey = `${blockId}_${originalWordIndex}`;
    setHumanConfirmedWords(prev => new Set(prev).add(wordKey));
    setActivePopup(null);
  };

  const handleEditClick = (blockIndex: number, wordIndex: number) => {
    setEditingWordIndex({ block: blockIndex, word: wordIndex });
    setEditingValue(blocksOfWordData[blockIndex][wordIndex].word);
    setActivePopup(null); // Hide correction bar while editing
  };

  const handleEditChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setEditingValue(event.target.value);
  };

  const handleEditSubmit = (blockIndex: number, wordIndex: number) => {
    if (editingValue.trim() === '') return; // Or handle as a deletion
    
    console.log('🎯 Heatmap manual edit request:', {
      blockIndex,
      wordIndex,
      editingValue,
      selectedDraft,
      currentWord: blocksOfWordData[blockIndex]?.[wordIndex]?.word,
      blockData: blocksOfWordData[blockIndex]?.slice(Math.max(0, wordIndex - 3), wordIndex + 4).map((w, i) => `${i + Math.max(0, wordIndex - 3)}: ${w.word}`)
    });
    
    // Use the new editing system if available
    if (onApplyEdit) {
      onApplyEdit(blockIndex, wordIndex, editingValue, 'manual_edit');
    } else {
      // Fallback to old system for backward compatibility
      const targetBlock = blocksOfWordData[blockIndex];
      const newWords = targetBlock.map((wordData, wIndex) => {
          if (wIndex === wordIndex) {
              return editingValue;
          }
          return wordData.word;
      });

      // Reconstruct the full text content
      const newBlocksOfText = blocksOfWordData.map((block, bIndex) => {
        if (bIndex === blockIndex) {
          return newWords.join(' ');
        }
        return block.map(w => w.word).join(' ');
      });

      onTextUpdate(newBlocksOfText.join('\n\n'));
    }

    // Mark as confirmed and exit editing mode
    const blockId = Object.keys(alignmentResult.alignment_results!.blocks)[blockIndex];
    const wordKey = `${blockId}_${wordIndex}`;
    setHumanConfirmedWords(prev => new Set(prev).add(wordKey));
    setEditingWordIndex(null);
  };


// NOTE: The interactive editing logic (handleWordClick, etc.) will need further
// refactoring to support multiple blocks, but the display logic below will work.
// I will simplify the rendering to focus on displaying the data correctly first.

  const activeWordData = activePopup ? blocksOfWordData[activePopup.block]?.[activePopup.word] : null;

  return (
    <div className="confidence-heatmap-viewer">
      {blocksOfWordData.map((block, blockIndex) => (
        <div key={blockIndex} className="heatmap-block">
          <p>
            {block.map((data, wordIndex) => {
              if (data.isEditing) {
                return (
                  <input
                    key={wordIndex}
                    type="text"
                    value={editingValue}
                    onChange={handleEditChange}
                    onBlur={() => handleEditSubmit(blockIndex, wordIndex)}
                    onKeyDown={(e) => e.key === 'Enter' && handleEditSubmit(blockIndex, wordIndex)}
                    autoFocus
                    className="word-edit-input"
                  />
                );
              }
              return (
                <span
                  key={wordIndex}
                  className="confidence-word"
                  style={{ backgroundColor: getConfidenceColor(data.confidence, data.isHumanConfirmed, data.hasBeenEdited) }}
                  title={`Confidence: ${(data.confidence * 100).toFixed(0)}%`}
                  onMouseEnter={(e) => handleWordHover(blockIndex, wordIndex, e)}
                  onMouseLeave={handleWordLeave}
                >
                  {data.word}{' '}
                </span>
              );
            })}
          </p>
        </div>
      ))}
      
      {activePopup && activeWordData && (
        <div
          className="quick-correction-bar"
          style={{
            position: 'fixed',
            left: `${popupPosition.x}px`,
            top: `${popupPosition.y}px`,
            transform: 'translateX(-50%)', // Position below the word
          }}
          onMouseEnter={handlePopupEnter}
          onMouseLeave={handlePopupLeave}
        >
          <div className="bar-option current" onClick={() => handleSelectAlternative(activePopup.block, activePopup.word, activeWordData.word)}>
            ✓ {activeWordData.word}
          </div>
          
          {activeWordData.alternatives.length > 0 && activeWordData.alternatives.map((alt, i) => (
            <div key={i} className="bar-option alternative" onClick={() => handleSelectAlternative(activePopup.block, activePopup.word, alt.word)}>
              {alt.word}
            </div>
          ))}

          <div className="bar-option edit-btn" onClick={() => handleEditClick(activePopup.block, activePopup.word)}>
            ✎ Edit
          </div>
          
          {/* Show a message if no alternatives are available but editing is still possible */}
          {activeWordData.alternatives.length === 0 && (
            <div className="bar-option info">
              No alternatives - use Edit to change
            </div>
          )}
        </div>
      )}
    </div>
  );
}; 