import React, { useState, useCallback, useMemo, useEffect } from 'react';

interface WordAlternative {
  word: string;
  source: string;
}

interface ConfidenceHeatmapViewerProps {
  text: string;
  wordConfidenceMap: Record<string, number>;
  redundancyAnalysis: {
    individual_results: Array<{
      success: boolean;
      text: string;
      tokens: number;
      error?: string;
    }>;
    consensus_text: string;
    best_formatted_text: string;
    best_result_index: number;
    word_alternatives: Record<string, string[]>;
  };
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
  wordConfidenceMap,
  redundancyAnalysis,
  onTextUpdate
}) => {
  const [editingWordIndex, setEditingWordIndex] = useState<number | null>(null);
  const [editingValue, setEditingValue] = useState<string>('');
  const [unlockedWords, setUnlockedWords] = useState<Set<number>>(new Set());
  const [humanConfirmedWords, setHumanConfirmedWords] = useState<Set<number>>(new Set());
  const [showPopup, setShowPopup] = useState<number | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Parse text into words with confidence data and alternatives
  const wordData = useMemo(() => {
    const words = text.match(/\S+/g) || [];
    const successfulResults = redundancyAnalysis.individual_results.filter(r => r.success);
    
    return words.map((word, index) => {
      const confidenceKey = `word_${index}`;
      const confidence = wordConfidenceMap[confidenceKey] || 0;
      
      // Find ACTUAL alternatives from other drafts
      const alternatives: WordAlternative[] = [];
      const seenWords = new Set<string>();
      
      successfulResults.forEach((result, resultIndex) => {
        const resultWords = result.text.match(/\S+/g) || [];
        if (resultWords[index] && resultWords[index].toLowerCase() !== word.toLowerCase()) {
          const altWord = resultWords[index];
          if (!seenWords.has(altWord.toLowerCase())) {
            seenWords.add(altWord.toLowerCase());
            alternatives.push({
              word: altWord,
              source: `Draft ${resultIndex + 1}`
            });
          }
        }
      });

      // Add consensus alternative if different
      const consensusWords = redundancyAnalysis.consensus_text.match(/\S+/g) || [];
      if (consensusWords[index] && consensusWords[index].toLowerCase() !== word.toLowerCase()) {
        const consensusWord = consensusWords[index];
        if (!seenWords.has(consensusWord.toLowerCase())) {
          alternatives.push({
            word: consensusWord,
            source: 'Consensus'
          });
        }
      }

      return {
        word,
        confidence,
        alternatives,
        isEditable: unlockedWords.has(index),
        isEditing: editingWordIndex === index,
        isHumanConfirmed: humanConfirmedWords.has(index)
      };
    });
  }, [text, wordConfidenceMap, redundancyAnalysis, unlockedWords, editingWordIndex, humanConfirmedWords]);

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
      return; // Don't show popup while editing
    }
    
    if (wordInfo.isEditable) {
      // Start editing if word is unlocked
      setEditingWordIndex(wordIndex);
      setEditingValue(wordInfo.word);
      setShowPopup(null);
    } else if (wordInfo.alternatives.length > 0 || wordInfo.confidence < 1.0) {
      // Show popup with alternatives and unlock option
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
    
    // Mark as human confirmed
    setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
    
    onTextUpdate(newText);
    setShowPopup(null);
  }, [wordData, text, onTextUpdate]);

  const handleConfirmCurrentWord = useCallback((wordIndex: number) => {
    // Mark current word as human confirmed without changing it
    setHumanConfirmedWords(prev => new Set([...prev, wordIndex]));
    setShowPopup(null);
  }, []);

  const handleEditingComplete = useCallback((wordIndex: number, newValue: string) => {
    if (newValue.trim() !== '' && newValue.trim() !== wordData[wordIndex]?.word) {
      const newWords = [...wordData.map(w => w.word)];
      newWords[wordIndex] = newValue.trim();
      const newText = rebuildTextWithFormatting(text, newWords);
      
      // Mark as human confirmed
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

  // Rebuild text while preserving formatting
  const rebuildTextWithFormatting = useCallback((originalText: string, newWords: string[]) => {
    let result = originalText;
    const wordMatches = [...originalText.matchAll(/\S+/g)];
    
    // Replace words from right to left to maintain indices
    for (let i = wordMatches.length - 1; i >= 0; i--) {
      if (newWords[i] !== undefined) {
        const match = wordMatches[i];
        result = result.substring(0, match.index!) + newWords[i] + result.substring(match.index! + match[0].length);
      }
    }
    
    return result;
  }, []);

  // Close popup when clicking outside
  useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.confidence-popup') && !target.closest('.confidence-word')) {
        setShowPopup(null);
      }
    };

    document.addEventListener('click', handleDocumentClick);
    return () => document.removeEventListener('click', handleDocumentClick);
  }, []);

  // Close editing when clicking outside
  useEffect(() => {
    const handleDocumentClick = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('.word-edit-input') && editingWordIndex !== null) {
        handleEditingComplete(editingWordIndex, editingValue);
      }
    };

    document.addEventListener('click', handleDocumentClick);
    return () => document.removeEventListener('click', handleDocumentClick);
  }, [editingWordIndex, editingValue, handleEditingComplete]);

  /**
   * 🔴 CRITICAL ALTERNATIVES EXTRACTION 🔴
   * =====================================
   * 
   * Extract actual alternative words from redundancy analysis.
   * Shows only REAL alternatives that differ from current word.
   * Includes current word as first option for human confirmation.
   */
  const getWordAlternatives = (wordId: string): string[] => {
    if (!redundancyAnalysis?.word_alternatives) return [];
    
    const alternatives = redundancyAnalysis.word_alternatives[wordId] || [];
    const currentWord = getCurrentWordText(wordId);
    
    if (alternatives.length === 0) return [];
    
    // Get unique alternatives (case-insensitive deduplication)
    const uniqueAlternatives = [];
    const seenLower = new Set();
    
    // Always include current word first for confirmation
    if (currentWord && !seenLower.has(currentWord.toLowerCase())) {
      uniqueAlternatives.push(currentWord);
      seenLower.add(currentWord.toLowerCase());
    }
    
    // Add actual alternatives that differ from current word
    for (const alt of alternatives) {
      const altLower = alt.toLowerCase();
      if (!seenLower.has(altLower) && altLower !== currentWord?.toLowerCase()) {
        uniqueAlternatives.push(alt);
        seenLower.add(altLower);
      }
    }
    
    // Only return if there are actual alternatives (more than just current word)
    return uniqueAlternatives.length > 1 ? uniqueAlternatives : [];
  };

  return (
    <div className="confidence-heatmap-viewer">
      <div className="heatmap-text-container">
        {(() => {
          // Split text while preserving whitespace and word boundaries
          const segments = text.split(/(\s+)/);
          let wordIndex = 0;
          
          return segments.map((segment, segmentIndex) => {
            if (segment.match(/\s+/)) {
              // Preserve whitespace
              return <span key={`space-${segmentIndex}`}>{segment}</span>;
            }
            
            if (!segment.trim()) {
              return null;
            }
            
            const currentWordIndex = wordIndex++;
            const wordInfo = wordData[currentWordIndex];
            
            if (!wordInfo) {
              return <span key={`word-${segmentIndex}`}>{segment}</span>;
            }

            if (wordInfo.isEditing) {
              return (
                <input
                  key={`edit-${segmentIndex}`}
                  type="text"
                  value={editingValue}
                  onChange={(e) => setEditingValue(e.target.value)}
                  onKeyDown={(e) => handleKeyDown(e, currentWordIndex)}
                  className="word-edit-input"
                  autoFocus
                  style={{ width: `${Math.max(editingValue.length * 8, 60)}px` }}
                />
              );
            }

            const hasInteraction = wordInfo.alternatives.length > 0 || wordInfo.confidence < 1.0;

            return (
              <span
                key={`word-${segmentIndex}`}
                className={`confidence-word ${wordInfo.isEditable ? 'editable' : ''} ${
                  hasInteraction ? 'clickable' : ''
                } ${wordInfo.isHumanConfirmed ? 'human-confirmed' : ''}`}
                style={{
                  backgroundColor: getConfidenceColor(wordInfo.confidence, wordInfo.isHumanConfirmed),
                  cursor: wordInfo.isEditable ? 'text' : hasInteraction ? 'pointer' : 'default'
                }}
                onClick={(e) => handleWordClick(currentWordIndex, e)}
                title={`Confidence: ${(wordInfo.confidence * 100).toFixed(0)}%${
                  wordInfo.alternatives.length > 0 ? ` • ${wordInfo.alternatives.length} alternatives` : ''
                }${wordInfo.isHumanConfirmed ? ' • Human confirmed' : ''}`}
              >
                {segment}
              </span>
            );
          }).filter(Boolean);
        })()}
      </div>

      {/* Confidence Popup */}
      {showPopup !== null && (
        <div 
          className="confidence-popup"
          style={{
            position: 'fixed',
            left: popupPosition.x,
            top: popupPosition.y,
            transform: 'translateX(-50%) translateY(-100%)',
            zIndex: 1000
          }}
        >
          <div className="popup-content">
            <div className="popup-word-info">
              <span className="popup-word">{wordData[showPopup]?.word}</span>
              <span className="popup-confidence">
                {((wordData[showPopup]?.confidence || 0) * 100).toFixed(0)}%
              </span>
            </div>
            
            {wordData[showPopup]?.alternatives.length > 0 && (
              <div className="popup-alternatives">
                {/* Current word as first option */}
                <button
                  className="alternative-option"
                  onClick={() => handleConfirmCurrentWord(showPopup)}
                  style={{ fontWeight: 'bold' }}
                >
                  {wordData[showPopup].word}
                </button>
                
                {wordData[showPopup].alternatives.map((alt, index) => (
                  <button
                    key={index}
                    className="alternative-option"
                    onClick={() => handleSelectAlternative(showPopup, alt.word)}
                  >
                    {alt.word}
                  </button>
                ))}
              </div>
            )}
            
            <button
              className="unlock-button"
              onClick={() => handleUnlockWord(showPopup)}
            >
              🔓
            </button>
          </div>
        </div>
      )}
    </div>
  );
}; 