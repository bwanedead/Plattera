import React, { useState, useCallback, useMemo, useEffect } from 'react';
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
  const [editingWordIndex, setEditingWordIndex] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState<string>('');
  const [unlockedWords, setUnlockedWords] = useState<Set<number>>(new Set());
  const [humanConfirmedWords, setHumanConfirmedWords] = useState<Set<number>>(new Set());
  const [showPopup, setShowPopup] = useState<number | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // This is now an array of arrays, one for each block
  const blocksOfWordData = useMemo<WordData[][]>(() => {
    if (!alignmentResult?.success) return [];

    const alignmentBlocks = alignmentResult.alignment_results?.blocks;
    const confidenceBlocks = alignmentResult.confidence_results?.block_confidences;

    if (!alignmentBlocks || !confidenceBlocks) return [];

    const processedBlocks = Object.keys(alignmentBlocks).sort().map(blockId => {
      const alignmentBlock = alignmentBlocks[blockId];
      const confidenceBlock = confidenceBlocks[blockId];
      
      if (!alignmentBlock || !confidenceBlock || !confidenceBlock.scores) return [];

      const displayedSequence = alignmentBlock.aligned_sequences[0]; // Display text from the first draft
      if (!displayedSequence) return [];

      return displayedSequence.tokens.map((token: string, index: number) => {
        if (token === '-') return null; // Don't create word data for gaps

        const confidence = confidenceBlock.scores[index] ?? 0;
        
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
          isEditable: false,
          isEditing: false,
          isHumanConfirmed: false,
        };
      }).filter((data): data is WordData => data !== null);
    });
    
    // Filter out any empty blocks that might have resulted from errors
    return processedBlocks.filter(block => block.length > 0);

  }, [alignmentResult]);


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

  const handleWordClick = useCallback((wordIndex: number, event: React.MouseEvent) => {
    const wordInfo = blocksOfWordData[0][wordIndex]; // Assuming we only have one block for now
    
    if (wordInfo.isEditing) {
      return;
    }
    
    if (wordInfo.isEditable) {
      setEditingWordIndex(wordIndex);
      setEditingValue(wordInfo.word);
      setShowPopup(null);
    } else if (wordInfo.alternatives.length > 0 || wordInfo.confidence < 1.0) {
      const rect = (event.target as HTMLElement).getBoundingClientRect();
      setPopupPosition({
        x: rect.left + rect.width / 2,
        y: rect.top - 10
      });
      setShowPopup(wordIndex);
    }
  }, [blocksOfWordData]);

  const handleUnlockWord = useCallback((wordIndex: number) => {
    setUnlockedWords(prev => new Set([...prev, wordIndex]));
    setShowPopup(null);
  }, []);

  const handleSelectAlternative = useCallback((wordIndex: number, alternative: string) => {
    const newWords = [...blocksOfWordData[0].map(w => w.word)];
    newWords[wordIndex] = alternative;
    const newText = rebuildTextWithFormatting(newWords);
    
    setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
    onTextUpdate(newText);
    setShowPopup(null);
  }, [blocksOfWordData, onTextUpdate]);

  const handleConfirmCurrentWord = useCallback((wordIndex: number) => {
    setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
    setShowPopup(null);
  }, []);

  const handleEditingComplete = useCallback((wordIndex: number, newValue: string) => {
    if (newValue.trim() !== '' && newValue.trim() !== blocksOfWordData[0][wordIndex]?.word) {
      const newWords = [...blocksOfWordData[0].map(w => w.word)];
      newWords[wordIndex] = newValue.trim();
      const newText = rebuildTextWithFormatting(newWords);
      
      setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
      onTextUpdate(newText);
    }
    setEditingWordIndex(null);
    setEditingValue('');
  }, [blocksOfWordData, onTextUpdate]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent, wordIndex: number) => {
    if (event.key === 'Enter') {
      handleEditingComplete(wordIndex, editingValue);
    } else if (event.key === 'Escape') {
      setEditingWordIndex(null);
      setEditingValue('');
    }
  }, [editingValue, handleEditingComplete]);

  const rebuildTextWithFormatting = useCallback((newWords: string[]) => {
    let result = '';
    const wordMatches = [...newWords.join(' ').matchAll(/\S+/g)];
    
    for (let i = wordMatches.length - 1; i >= 0; i--) {
      if (newWords[i] !== undefined) {
        const match = wordMatches[i];
        result = result.substring(0, match.index!) + newWords[i] + result.substring(match.index! + match[0].length);
      }
    }
    
    return result;
  }, []);

  useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.confidence-popup') && !target.closest('.confidence-word')) {
        setShowPopup(null);
      }
      if (!target.closest('.word-edit-input') && editingWordIndex !== null) {
        handleEditingComplete(editingWordIndex, editingValue);
      }
    };

    document.addEventListener('click', handleDocumentClick);
    return () => document.removeEventListener('click', handleDocumentClick);
  }, [editingWordIndex, editingValue, handleEditingComplete]);

  return (
    <div className="confidence-heatmap-viewer">
      {blocksOfWordData.map((block, blockIndex) => (
        <div key={blockIndex} className="heatmap-block">
          <p>
            {block.map((data, wordIndex) => (
              <span
                key={wordIndex}
                className="confidence-word"
                style={{ backgroundColor: getConfidenceColor(data.confidence, data.isHumanConfirmed) }}
                title={`Confidence: ${(data.confidence * 100).toFixed(0)}%`}
              >
                {data.word}{' '}
              </span>
            ))}
          </p>
        </div>
      ))}

      {showPopup !== null && (
        <div 
          className="confidence-popup" 
          style={{ 
            position: 'fixed', 
            left: `${popupPosition.x}px`, 
            top: `${popupPosition.y}px`,
            transform: 'translate(-50%, -100%)',
          }}
        >
          <div className="popup-header">
            <strong>'{blocksOfWordData[0][showPopup].word}'</strong> - Conf: {Math.round(blocksOfWordData[0][showPopup].confidence * 100)}%
          </div>
          <div className="popup-actions">
            <button onClick={() => handleConfirmCurrentWord(showPopup)}>Confirm Current</button>
            <button onClick={() => handleUnlockWord(showPopup)}>Unlock & Edit</button>
          </div>
          {blocksOfWordData[0][showPopup].alternatives.length > 0 && (
            <div className="popup-alternatives">
              <hr />
              <strong>Alternatives:</strong>
              <ul>
                {blocksOfWordData[0][showPopup].alternatives.map((alt, i) => (
                  <li key={i} onClick={() => handleSelectAlternative(showPopup, alt.word)}>
                    <span className="alt-word">{alt.word}</span>
                    <span className="alt-source">({alt.source})</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}; 