import React, { useState, useCallback, useMemo, useEffect } from 'react';
import { AlignmentResult } from '../../types/imageProcessing';

interface WordAlternative {
  word: string;
  source: string; // e.g., "Draft 1", "Consensus"
}

interface ConfidenceHeatmapViewerProps {
  text: string;
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
  text,
  alignmentResult,
  onTextUpdate
}) => {
  const [editingWordIndex, setEditingWordIndex] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState<string>('');
  const [unlockedWords, setUnlockedWords] = useState<Set<number>>(new Set());
  const [humanConfirmedWords, setHumanConfirmedWords] = useState<Set<number>>(new Set());
  const [showPopup, setShowPopup] = useState<number | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  const wordData = useMemo<WordData[]>(() => {
    if (!alignmentResult?.success) {
      return (text.match(/\S+/g) || []).map(word => ({
        word,
        confidence: 0,
        alternatives: [],
        isEditable: false,
        isEditing: false,
        isHumanConfirmed: false,
      }));
    }
  
    const words = text.match(/\S+/g) || [];
    const confidenceBlock = alignmentResult.confidence_results?.block_confidences?.legal_text;
    const alignmentBlock = alignmentResult.alignment_results?.blocks?.legal_text;
  
    if (!confidenceBlock || !alignmentBlock || !confidenceBlock.scores) {
        return (text.match(/\S+/g) || []).map(word => ({
            word,
            confidence: 0,
            alternatives: [],
            isEditable: false,
            isEditing: false,
            isHumanConfirmed: false,
          }));
    }
  
    // Reconstruct the token data with confidence scores
    const tokenData = confidenceBlock.scores.map((score: number, index: number) => ({
      // For now, we assume the token from the first draft is the one displayed.
      // A more robust solution might need to check which draft is selected.
      token: alignmentBlock.aligned_sequences[0]?.tokens[index] || '',
      confidence: score,
      position: index,
    }));
  
    const confidenceMap = new Map<number, number>();
    tokenData.forEach((tokenInfo: any) => {
      confidenceMap.set(tokenInfo.position, tokenInfo.confidence);
    });
  
    return words.map((word, index) => {
      const confidence = confidenceMap.get(index) ?? 0;
  
      const alternatives: WordAlternative[] = [];
      const seenWords = new Set<string>([word.toLowerCase()]);
  
      alignmentBlock.aligned_sequences?.forEach((seq: any) => {
        const altToken = seq.tokens?.[index];
        if (altToken && altToken !== '-' && !seenWords.has(altToken.toLowerCase())) {
          alternatives.push({ word: altToken, source: seq.draft_id });
          seenWords.add(altToken.toLowerCase());
        }
      });
  
      return {
        word,
        confidence,
        alternatives,
        isEditable: unlockedWords.has(index),
        isEditing: editingWordIndex === index,
        isHumanConfirmed: humanConfirmedWords.has(index),
      };
    });
  }, [text, alignmentResult, unlockedWords, editingWordIndex, humanConfirmedWords]);

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
    const wordInfo = wordData[wordIndex];
    
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
  }, [wordData]);

  const handleUnlockWord = useCallback((wordIndex: number) => {
    setUnlockedWords(prev => new Set([...prev, wordIndex]));
    setShowPopup(null);
  }, []);

  const handleSelectAlternative = useCallback((wordIndex: number, alternative: string) => {
    const newWords = [...wordData.map(w => w.word)];
    newWords[wordIndex] = alternative;
    const newText = rebuildTextWithFormatting(text, newWords);
    
    setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
    onTextUpdate(newText);
    setShowPopup(null);
  }, [wordData, text, onTextUpdate]);

  const handleConfirmCurrentWord = useCallback((wordIndex: number) => {
    setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
    setShowPopup(null);
  }, []);

  const handleEditingComplete = useCallback((wordIndex: number, newValue: string) => {
    if (newValue.trim() !== '' && newValue.trim() !== wordData[wordIndex]?.word) {
      const newWords = [...wordData.map(w => w.word)];
      newWords[wordIndex] = newValue.trim();
      const newText = rebuildTextWithFormatting(text, newWords);
      
      setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
      onTextUpdate(newText);
    }
    setEditingWordIndex(null);
    setEditingValue('');
  }, [wordData, text, onTextUpdate]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent, wordIndex: number) => {
    if (event.key === 'Enter') {
      handleEditingComplete(wordIndex, editingValue);
    } else if (event.key === 'Escape') {
      setEditingWordIndex(null);
      setEditingValue('');
    }
  }, [editingValue, handleEditingComplete]);

  const rebuildTextWithFormatting = useCallback((originalText: string, newWords: string[]) => {
    let result = originalText;
    const wordMatches = [...originalText.matchAll(/\S+/g)];
    
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
      <p>
        {wordData.map((data, index) => (
          <React.Fragment key={index}>
            {data.isEditing ? (
              <input
                type="text"
                value={editingValue}
                onChange={(e) => setEditingValue(e.target.value)}
                onKeyDown={(e) => handleKeyDown(e, index)}
                onBlur={() => handleEditingComplete(index, editingValue)}
                autoFocus
                className="word-edit-input"
                style={{ width: `${Math.max(50, editingValue.length * 8)}px` }}
              />
            ) : (
              <span
                className="confidence-word"
                style={{ backgroundColor: getConfidenceColor(data.confidence, data.isHumanConfirmed) }}
                onClick={(e) => handleWordClick(index, e)}
              >
                {data.word}
              </span>
            )}
            {' '}
          </React.Fragment>
        ))}
      </p>

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
            <strong>'{wordData[showPopup].word}'</strong> - Conf: {Math.round(wordData[showPopup].confidence * 100)}%
          </div>
          <div className="popup-actions">
            <button onClick={() => handleConfirmCurrentWord(showPopup)}>Confirm Current</button>
            <button onClick={() => handleUnlockWord(showPopup)}>Unlock & Edit</button>
          </div>
          {wordData[showPopup].alternatives.length > 0 && (
            <div className="popup-alternatives">
              <hr />
              <strong>Alternatives:</strong>
              <ul>
                {wordData[showPopup].alternatives.map((alt, i) => (
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