import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

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
  };
  onUndoEdit?: () => void;
  onRedoEdit?: () => void;
  onResetToOriginal?: () => void;
}

interface WordData {
  word: string;
  confidence: number;
  alternatives: WordAlternative[];
  isEditable: boolean;
  isEditing: boolean;
  isHumanConfirmed: boolean;
}

export const ConfidenceHeatmapViewer: React.FC<ConfidenceHeatmapViewerProps> = ({
  alignmentResult,
  onTextUpdate,
  onApplyEdit,
  editableDraftState,
  onUndoEdit,
  onRedoEdit,
  onResetToOriginal
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

    // Use edited text if available, otherwise use original alignment data
    const hasEdits = editableDraftState?.hasUnsavedChanges;
    const editedBlockTexts = editableDraftState?.editedDraft?.blockTexts;

    const processedBlocks = Object.keys(alignmentBlocks).sort().map((blockId, blockIndex) => {
      const alignmentBlock = alignmentBlocks[blockId];
      const confidenceBlock = confidenceBlocks[blockId];
      
      if (!alignmentBlock || !confidenceBlock || !confidenceBlock.scores) return [];

      const displayedSequence = alignmentBlock.aligned_sequences[0]; // Display text from the first draft
      if (!displayedSequence) return [];

      // If we have edits, use the edited text for this block, otherwise use original tokens
      let displayTokens: string[];
      
      if (hasEdits && editedBlockTexts && editedBlockTexts[blockIndex]) {
        // Use edited text, but ensure it's properly formatted
        let editedText = editedBlockTexts[blockIndex];
        
        console.log(`🔍 Raw edited text for block ${blockIndex}:`, editedText);
        
        // FIXED: Improved JSON detection and parsing
        if (typeof editedText === 'string') {
          const trimmedText = editedText.trim();
          
          // Check for JSON patterns (starts with { or [, or contains JSON-like structure)
          if (trimmedText.startsWith('{') || trimmedText.startsWith('[') || 
              (trimmedText.includes('"') && trimmedText.includes(':'))) {
            try {
              // Try to parse as JSON first
              const parsedJson = JSON.parse(editedText);
              
              if (parsedJson && typeof parsedJson === 'object' && parsedJson.content) {
                editedText = parsedJson.content;
                console.log('✅ Parsed JSON content:', editedText);
              } else if (parsedJson && typeof parsedJson === 'string') {
                editedText = parsedJson;
                console.log('✅ Parsed JSON string:', editedText);
              } else if (Array.isArray(parsedJson)) {
                // Handle array case
                editedText = parsedJson.join(' ');
                console.log('✅ Parsed JSON array:', editedText);
              }
                          } catch (e) {
                // If it's not valid JSON, use as-is
                console.log('📝 Edited text is not JSON, using as-is:', e instanceof Error ? e.message : 'Unknown error');
              }
          }
        }
        
        // Split into words, ensuring we have a valid string
        displayTokens = (editedText || '').split(' ').filter(word => word.length > 0);
        console.log(`🔄 Using edited text for block ${blockIndex}:`, displayTokens);
      } else {
        // Use original alignment tokens
        displayTokens = displayedSequence.tokens.filter((token: string) => token !== '-');
        console.log(`📝 Using original text for block ${blockIndex}:`, displayTokens);
      }

      return displayTokens.map((token: string, index: number) => {
        const confidence = confidenceBlock.scores[index] ?? 0;
        const wordKey = `${blockId}_${index}`;
        
        // Build alternatives from original alignment data
        const alternatives: WordAlternative[] = [];
        const seenWords = new Set<string>([token.toLowerCase()]);

        alignmentBlock.aligned_sequences?.forEach((seq: any) => {
          const altToken = seq.tokens?.[index];
          if (altToken && altToken !== '-' && !seenWords.has(altToken.toLowerCase())) {
            alternatives.push({ word: altToken, source: seq.draft_id });
            seenWords.add(altToken.toLowerCase());
          }
        });

        return {
          word: token,
          confidence,
          alternatives,
          isEditable: false, // For now, direct editing is complex
          isEditing: editingWordIndex?.block === blockIndex && editingWordIndex?.word === index,
          isHumanConfirmed: humanConfirmedWords.has(wordKey),
        };
      });
    });
    
    // Filter out any empty blocks that might have resulted from errors
    return processedBlocks.filter(block => block && block.length > 0);

  }, [alignmentResult, editingWordIndex, humanConfirmedWords, editableDraftState]);


  const getConfidenceColor = useCallback((confidence: number, isHumanConfirmed: boolean) => {
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
    // Use the new editing system if available
    if (onApplyEdit) {
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
                  style={{ backgroundColor: getConfidenceColor(data.confidence, data.isHumanConfirmed) }}
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