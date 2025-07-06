import React, { useState, useCallback, useMemo, useEffect, useRef } from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

interface WordAlternative {
  word: string;
  source: string; // e.g., "Draft 1", "Consensus"
}

interface ConfidenceHeatmapViewerProps {
  alignmentResult: AlignmentResult;
  onTextUpdate: (newText: string) => void;
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
  onTextUpdate
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

    const processedBlocks = Object.keys(alignmentBlocks).sort().map((blockId, blockIndex) => {
      const alignmentBlock = alignmentBlocks[blockId];
      const confidenceBlock = confidenceBlocks[blockId];
      
      if (!alignmentBlock || !confidenceBlock || !confidenceBlock.scores) return [];

      const displayedSequence = alignmentBlock.aligned_sequences[0]; // Display text from the first draft
      if (!displayedSequence) return [];

      return displayedSequence.tokens.map((token: string, index: number) => {
        if (token === '-') return null; // Don't create word data for gaps

        const confidence = confidenceBlock.scores[index] ?? 0;
        const wordKey = `${blockId}_${index}`;
        
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
      }).filter((data: WordData | null): data is WordData => data !== null);
    });
    
    // Filter out any empty blocks that might have resulted from errors
    return processedBlocks.filter(block => block && block.length > 0);

  }, [alignmentResult, editingWordIndex, humanConfirmedWords]);


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
    if (wordInfo && (wordInfo.alternatives.length > 0 || wordInfo.confidence < 1.0) && !wordInfo.isHumanConfirmed) {
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
    // Reconstruct the full text with the chosen alternative
    const newBlocksOfWordData = blocksOfWordData.map((block, bIndex) => {
      if (bIndex === blockIndex) {
        const newWords = [...block.map(w => w.word)];
        newWords[wordIndex] = newWord;
        return newWords;
      }
      return block.map(w => w.word);
    });

    const newText = newBlocksOfWordData.map(block => block.join(' ')).join('\n\n');
    onTextUpdate(newText); // Pass full updated text up

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
    
    // Create a new list of words for the block
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
          
          {activeWordData.alternatives.map((alt, i) => (
            <div key={i} className="bar-option alternative" onClick={() => handleSelectAlternative(activePopup.block, activePopup.word, alt.word)}>
              {alt.word}
            </div>
          ))}

          <div className="bar-option edit-btn" onClick={() => handleEditClick(activePopup.block, activePopup.word)}>
            ✎ Edit
          </div>
        </div>
      )}
    </div>
  );
}; 