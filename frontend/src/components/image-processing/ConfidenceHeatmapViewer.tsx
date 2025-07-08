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
  const [activePopup, setActivePopup] = useState<{ block: number; word: number } | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [editingWordIndex, setEditingWordIndex] = useState<{ block: number; word: number } | null>(null);
  const [editingValue, setEditingValue] = useState('');
  const [humanConfirmedWords, setHumanConfirmedWords] = useState<Set<string>>(new Set());
  const [hoveredWord, setHoveredWord] = useState<{ block: number; word: number } | null>(null);
  
  const hidePopupTimer = useRef<NodeJS.Timeout | null>(null);
  const showPopupTimer = useRef<NodeJS.Timeout | null>(null);
  const hasEnteredPopup = useRef<boolean>(false); // Track if user has entered popup

  // This is now an array of arrays, one for each block
  const blocksOfWordData = useMemo<WordData[][]>(() => {
    if (!alignmentResult?.success) return [];

    const alignmentBlocks = alignmentResult.alignment_results?.blocks;
    if (!alignmentBlocks) return [];

    const processedBlocks = Object.keys(alignmentBlocks).sort().map((blockId, blockIndex) => {
      const alignmentBlock = alignmentBlocks[blockId];
      if (!alignmentBlock || !alignmentBlock.aligned_sequences) return [];

      // === CALCULATE AGREEMENT PERCENTAGE FROM ALIGNMENT TABLE ===
      console.log(`🌈 DYNAMIC HEATMAP CALCULATION ► Block ${blockIndex}`);
      
      const sequences = alignmentBlock.aligned_sequences;
      if (!sequences || sequences.length < 2) return [];

      const maxLength = Math.max(...sequences.map((seq: any) => seq.tokens?.length || 0));
      const totalDrafts = sequences.length;
      
      console.log(`🌈 Block ${blockIndex}: ${totalDrafts} drafts, ${maxLength} positions`);

      const wordDataForBlock: WordData[] = [];
      
      for (let position = 0; position < maxLength; position++) {
        // Get all tokens at this position
        const tokensAtPosition = sequences.map((seq: any) => seq.tokens?.[position] || '-');
        
        // Filter out gaps and empty tokens
        const validTokens = tokensAtPosition.filter(token => token && token !== '-');
        
        if (validTokens.length === 0) continue;
        
        // Calculate agreement percentage
        const tokenCounts = new Map<string, number>();
        validTokens.forEach(token => {
          const normalizedToken = token.toLowerCase().trim();
          tokenCounts.set(normalizedToken, (tokenCounts.get(normalizedToken) || 0) + 1);
        });
        
        // Find the most common token and its count
        let maxCount = 0;
        let consensusToken = validTokens[0];
        
        for (const [token, count] of tokenCounts.entries()) {
          if (count > maxCount) {
            maxCount = count;
            // Find the original case version of this token
            consensusToken = validTokens.find(t => t.toLowerCase().trim() === token) || token;
          }
        }
        
        // Calculate agreement percentage (0.0 to 1.0)
        const agreementPercentage = maxCount / totalDrafts;
        
        // Use selected draft token if available, otherwise use consensus
        let displayToken = consensusToken;
        if (typeof selectedDraft === 'number' && selectedDraft < sequences.length) {
          const selectedToken = sequences[selectedDraft]?.tokens?.[position];
          if (selectedToken && selectedToken !== '-') {
            displayToken = selectedToken;
          }
        }
        
        // Create alternatives from all unique tokens
        const alternatives: WordAlternative[] = [];
        const seenTokens = new Set<string>();
        
        sequences.forEach((seq: any, seqIndex: number) => {
          const token = seq.tokens?.[position];
          if (token && token !== '-') {
            const normalizedToken = token.toLowerCase().trim();
            if (!seenTokens.has(normalizedToken)) {
              alternatives.push({
                word: token,
                source: seq.draft_id || `Draft ${seqIndex + 1}`
              });
              seenTokens.add(normalizedToken);
            }
          }
        });

        // Log detailed agreement analysis
        if (agreementPercentage < 1.0) {
          console.log(`🌈 DISAGREEMENT at position ${position}:`, {
            totalDrafts,
            validTokens,
            tokenCounts: Object.fromEntries(tokenCounts),
            maxCount,
            agreementPercentage: `${(agreementPercentage * 100).toFixed(1)}%`,
            consensusToken,
            displayToken,
            alternatives: alternatives.map(a => a.word)
          });
        }

        const wordKey = `${blockId}_${position}`;
        const hasBeenEdited = editableDraftState?.editHistory?.some((edit: any) => 
          edit.blockIndex === blockIndex && edit.tokenIndex === position
        ) || false;

        wordDataForBlock.push({
          word: displayToken,
          confidence: agreementPercentage, // Use actual agreement percentage
          alternatives: alternatives,
          isEditable: false,
          isEditing: editingWordIndex?.block === blockIndex && editingWordIndex?.word === position,
          isHumanConfirmed: humanConfirmedWords.has(wordKey),
          hasBeenEdited: hasBeenEdited
        });
      }

      // Apply edits if available
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

      const disagreementCount = wordDataForBlock.filter(w => w.confidence < 1.0).length;
      console.log(`🌈 Block ${blockIndex} processed: ${wordDataForBlock.length} tokens, ${disagreementCount} disagreements`);
      
      return wordDataForBlock;
    });
    
    return processedBlocks.filter(block => block && block.length > 0);

  }, [alignmentResult, editingWordIndex, humanConfirmedWords, editableDraftState, selectedDraft]);

  // Dynamic color gradient: Green → Yellow → Red based on agreement percentage
  const getConfidenceColor = useCallback((confidence: number, isHumanConfirmed: boolean, hasBeenEdited: boolean) => {
    if (hasBeenEdited) {
      return 'rgba(59, 130, 246, 0.35)'; // Blue background for edited words
    }
    
    if (isHumanConfirmed) {
      return 'rgba(16, 185, 129, 0.3)'; // Emerald green for human-confirmed
    }
    
    // Create smooth gradient from green to yellow to red
    // confidence is now the actual agreement percentage (0.0 to 1.0)
    
    if (confidence >= 0.95) {
      // Very high agreement (95-100%) - Pure green
      const intensity = 0.15 + (confidence - 0.95) * 0.1; // 0.15 to 0.25
      return `rgba(34, 197, 94, ${intensity})`;
    } else if (confidence >= 0.8) {
      // High agreement (80-95%) - Green to light green
      const intensity = 0.2 + (confidence - 0.8) * 0.2; // 0.2 to 0.4
      return `rgba(74, 222, 128, ${intensity})`;
    } else if (confidence >= 0.6) {
      // Medium-high agreement (60-80%) - Light green to yellow-green
      const ratio = (confidence - 0.6) / 0.2; // 0 to 1
      const red = Math.round(154 + ratio * (255 - 154));   // 154 to 255
      const green = Math.round(222 + ratio * (255 - 222)); // 222 to 255
      const blue = Math.round(128 - ratio * 128);          // 128 to 0
      return `rgba(${red}, ${green}, ${blue}, 0.35)`;
    } else if (confidence >= 0.4) {
      // Medium agreement (40-60%) - Yellow-green to yellow
      const ratio = (confidence - 0.4) / 0.2; // 0 to 1
      const red = Math.round(255);                      // Pure yellow
      const green = Math.round(255);                    // Pure yellow
      const blue = Math.round(0);                       // Pure yellow
      return `rgba(${red}, ${green}, ${blue}, 0.4)`;
    } else if (confidence >= 0.2) {
      // Low agreement (20-40%) - Yellow to orange
      const ratio = (confidence - 0.2) / 0.2; // 0 to 1
      const red = Math.round(255);                      // 255 constant
      const green = Math.round(165 + ratio * (255 - 165)); // 165 to 255
      const blue = Math.round(0);                       // 0 constant
      return `rgba(${red}, ${green}, ${blue}, 0.45)`;
    } else {
      // Very low agreement (0-20%) - Orange to red
      const ratio = confidence / 0.2; // 0 to 1
      const red = Math.round(255);                      // 255 constant
      const green = Math.round(ratio * 165);            // 0 to 165
      const blue = Math.round(0);                       // 0 constant
      return `rgba(${red}, ${green}, ${blue}, 0.5)`;
    }
  }, []);

  const handleWordHover = (blockIndex: number, wordIndex: number, event: React.MouseEvent) => {
    const wordInfo = blocksOfWordData[blockIndex]?.[wordIndex];
    
    // Set hovered word for highlighting
    setHoveredWord({ block: blockIndex, word: wordIndex });
    
    if (wordInfo && !wordInfo.isHumanConfirmed) {
      // Clear any existing timers
      if (hidePopupTimer.current) {
        clearTimeout(hidePopupTimer.current);
      }
      if (showPopupTimer.current) {
        clearTimeout(showPopupTimer.current);
      }
      
      // Reset popup entry tracking
      hasEnteredPopup.current = false;
      
      // Add delay before showing popup (200ms)
      showPopupTimer.current = setTimeout(() => {
      const rect = (event.target as HTMLElement).getBoundingClientRect();
        const popupWidth = 180; // Estimated popup width
        const windowWidth = window.innerWidth;
        
        // Edge detection: position popup on left if it would extend past right edge
        const shouldPositionLeft = rect.right + popupWidth + 8 > windowWidth;
        
        let x, y;
        if (shouldPositionLeft) {
          // Position closer to the word when on the left side
          x = rect.left - popupWidth + rect.width + 4; // Much closer to the word
          y = rect.top - 4;
        } else {
          x = rect.right + 8; // 8px to the right of the word
          y = rect.top - 4;
        }
        
        // Also check if popup would extend past bottom edge
        const popupHeight = 120; // Estimated popup height
        if (y + popupHeight > window.innerHeight) {
          y = window.innerHeight - popupHeight - 8;
        }
        
        setPopupPosition({ x, y });
      setActivePopup({ block: blockIndex, word: wordIndex });
      }, 200); // 200ms delay
    }
  };

  const handleWordLeave = () => {
    // Clear hovered word highlighting
    setHoveredWord(null);
    
    // Clear show timer if word is left before popup appears
    if (showPopupTimer.current) {
      clearTimeout(showPopupTimer.current);
    }
    
    // Longer delay to allow cursor movement to popup
    hidePopupTimer.current = setTimeout(() => {
      setActivePopup(null);
    }, 800); // 800ms for easier cursor movement
  };

  const handlePopupEnter = () => {
    hasEnteredPopup.current = true; // Mark that user has entered popup
    if (hidePopupTimer.current) {
      clearTimeout(hidePopupTimer.current);
    }
  };

  const handlePopupLeave = () => {
    // Much faster hide if user has already entered popup
    const hideDelay = hasEnteredPopup.current ? 50 : 200; // Almost instant vs small delay
    
    hidePopupTimer.current = setTimeout(() => {
    setActivePopup(null);
    }, hideDelay);
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
    setActivePopup(null);
  };

  const handleEditChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    setEditingValue(event.target.value);
  };

  const handleEditSubmit = (blockIndex: number, wordIndex: number) => {
    if (editingValue.trim() === '') return;
    
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
              
              const isHovered = hoveredWord?.block === blockIndex && hoveredWord?.word === wordIndex;
              
              return (
                <span
                  key={wordIndex}
                  className={`confidence-word ${isHovered ? 'hovered' : ''}`}
                  style={{ backgroundColor: getConfidenceColor(data.confidence, data.isHumanConfirmed, data.hasBeenEdited) }}
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
          className="word-suggestion-popup"
          style={{
            position: 'fixed',
            left: `${popupPosition.x}px`,
            top: `${popupPosition.y}px`,
            zIndex: 1000,
          }}
          onMouseEnter={handlePopupEnter}
          onMouseLeave={handlePopupLeave}
        >
          {/* Confidence header */}
          <div className="popup-header">
            <span className="confidence-badge">{(activeWordData.confidence * 100).toFixed(0)}%</span>
          </div>
          
          {/* Current word option */}
          <div 
            className="suggestion-option current-word"
            onClick={() => handleSelectAlternative(activePopup.block, activePopup.word, activeWordData.word)}
          >
            <span className="option-icon">✓</span>
            <div className="option-content">
              <span className="option-text">{activeWordData.word}</span>
            </div>
          </div>
          
          {/* Alternative options */}
          {activeWordData.alternatives.length > 1 && activeWordData.alternatives
            .filter(alt => alt.word.toLowerCase() !== activeWordData.word.toLowerCase())
            .map((alt, i) => (
              <div 
                key={i} 
                className="suggestion-option alternative"
                onClick={() => handleSelectAlternative(activePopup.block, activePopup.word, alt.word)}
              >
                <span className="option-icon">↻</span>
                <div className="option-content">
                  <span className="option-text">{alt.word}</span>
                  <span className="option-source">{alt.source}</span>
                </div>
              </div>
            ))}

          {/* Manual edit option */}
          <div 
            className="suggestion-option edit-option"
            onClick={() => handleEditClick(activePopup.block, activePopup.word)}
          >
            <span className="option-icon">✎</span>
            <div className="option-content">
              <span className="option-text">Edit</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}; 