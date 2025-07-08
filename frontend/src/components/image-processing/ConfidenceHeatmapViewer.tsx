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
    if (!alignmentBlocks) return [];

    const processedBlocks = Object.keys(alignmentBlocks).sort().map((blockId, blockIndex) => {
      const alignmentBlock = alignmentBlocks[blockId];
      if (!alignmentBlock || !alignmentBlock.aligned_sequences) return [];

      // === CALCULATE MISALIGNMENTS FROM ALIGNMENT TABLE ===
      console.log(`🔍 HEATMAP MISALIGNMENT CALCULATION ► Block ${blockIndex}`);
      
      // Extract all aligned sequences (Draft_1, Draft_2, Draft_3, etc.)
      const sequences = alignmentBlock.aligned_sequences;
      if (!sequences || sequences.length < 2) return [];

      // Get the maximum length to handle all positions
      const maxLength = Math.max(...sequences.map((seq: any) => seq.tokens?.length || 0));
      console.log(`🔍 Block ${blockIndex} has ${sequences.length} drafts with max ${maxLength} tokens`);

      // For each position, check if all drafts agree
      const wordDataForBlock: WordData[] = [];
      
      for (let position = 0; position < maxLength; position++) {
        // Get tokens at this position from all drafts
        const tokensAtPosition = sequences.map((seq: any) => seq.tokens?.[position] || '-');
        
        // Filter out gaps and empty tokens
        const validTokens = tokensAtPosition.filter(token => token && token !== '-');
        
        if (validTokens.length === 0) continue; // Skip if no valid tokens
        
        // Check if all valid tokens are the same (case-insensitive)
        const uniqueTokens = [...new Set(validTokens.map(t => t.toLowerCase()))];
        const hasMismatch = uniqueTokens.length > 1;
        
        // Calculate confidence based on agreement
        const confidence = hasMismatch ? 0.3 : 0.95; // Low confidence for mismatches
        
        // Use the token from the selected draft, or first valid token
        let displayToken = validTokens[0]; // Default to first valid token
        
        if (typeof selectedDraft === 'number' && selectedDraft < sequences.length) {
          const selectedToken = sequences[selectedDraft]?.tokens?.[position];
          if (selectedToken && selectedToken !== '-') {
            displayToken = selectedToken;
          }
        }
        
        // Create alternatives array from all different tokens
        const alternatives: WordAlternative[] = [];
        const seenTokens = new Set<string>();
        
        sequences.forEach((seq: any, seqIndex: number) => {
          const token = seq.tokens?.[position];
          if (token && token !== '-' && !seenTokens.has(token.toLowerCase())) {
            alternatives.push({
              word: token,
              source: seq.draft_id || `Draft ${seqIndex + 1}`
            });
            seenTokens.add(token.toLowerCase());
          }
        });

        // Log mismatches for debugging
        if (hasMismatch) {
          console.log(`🔍 MISMATCH at position ${position}:`, {
            tokens: tokensAtPosition,
            validTokens: validTokens,
            uniqueTokens: uniqueTokens,
            displayToken: displayToken,
            confidence: confidence,
            alternatives: alternatives
          });
        }

        const wordKey = `${blockId}_${position}`;
        const hasBeenEdited = editableDraftState?.editHistory?.some((edit: any) => 
          edit.blockIndex === blockIndex && edit.tokenIndex === position
        ) || false;

        wordDataForBlock.push({
          word: displayToken,
          confidence: confidence,
          alternatives: alternatives,
          isEditable: false,
          isEditing: editingWordIndex?.block === blockIndex && editingWordIndex?.word === position,
          isHumanConfirmed: humanConfirmedWords.has(wordKey),
          hasBeenEdited: hasBeenEdited
        });
      }

      // Apply edits if we have them
      if (editableDraftState?.hasUnsavedChanges && 
          editableDraftState?.editHistory && 
          editableDraftState?.editedFromDraft === selectedDraft) {
        
        const relevantEdits = editableDraftState.editHistory.filter((edit: any) => 
          edit.blockIndex === blockIndex
        );
        
        relevantEdits.forEach((edit: any) => {
          if (edit.tokenIndex < wordDataForBlock.length) {
            wordDataForBlock[edit.tokenIndex].word = edit.newValue;
            wordDataForBlock[edit.tokenIndex].hasBeenEdited = true;
          }
        });
      }

      console.log(`🔍 Block ${blockIndex} processed: ${wordDataForBlock.length} tokens, ${wordDataForBlock.filter(w => w.confidence < 0.5).length} mismatches`);
      return wordDataForBlock;
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
    
    // Enhanced color coding for misalignments
    if (confidence >= 0.9) {
      return 'rgba(34, 197, 94, 0.15)'; // Light green for perfect agreement
    } else if (confidence >= 0.7) {
      return 'rgba(255, 193, 7, 0.2)'; // Yellow for minor disagreements
    } else if (confidence >= 0.5) {
      return 'rgba(255, 152, 0, 0.3)'; // Orange for moderate disagreements
    } else {
      return 'rgba(220, 53, 69, 0.4)'; // Strong red for major misalignments
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