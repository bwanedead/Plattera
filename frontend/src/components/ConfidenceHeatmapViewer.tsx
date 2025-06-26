import React, { useState, useCallback, useMemo } from 'react';

interface WordAlternative {
  word: string;
  source: string;
  confidence: number;
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
  };
  onTextUpdate: (newText: string) => void;
}

interface WordData {
  word: string;
  confidence: number;
  alternatives: WordAlternative[];
  isEditable: boolean;
  isEditing: boolean;
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
  const [showPopup, setShowPopup] = useState<number | null>(null);
  const [popupPosition, setPopupPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });

  // Parse text into words with confidence data and alternatives
  const wordData = useMemo(() => {
    const words = text.match(/\S+/g) || [];
    const successfulResults = redundancyAnalysis.individual_results.filter(r => r.success);
    
    return words.map((word, index) => {
      const confidenceKey = `word_${index}`;
      const confidence = wordConfidenceMap[confidenceKey] || 0;
      
      // Find alternatives from other drafts
      const alternatives: WordAlternative[] = [];
      
      successfulResults.forEach((result, resultIndex) => {
        const resultWords = result.text.match(/\S+/g) || [];
        if (resultWords[index] && resultWords[index] !== word) {
          alternatives.push({
            word: resultWords[index],
            source: `Draft ${resultIndex + 1}`,
            confidence: 0.8 // Approximate confidence for alternatives
          });
        }
      });

      // Add consensus alternative if different
      const consensusWords = redundancyAnalysis.consensus_text.match(/\S+/g) || [];
      if (consensusWords[index] && consensusWords[index] !== word) {
        alternatives.push({
          word: consensusWords[index],
          source: 'Consensus',
          confidence: 0.9
        });
      }

      return {
        word,
        confidence,
        alternatives: alternatives.filter((alt, idx, arr) => 
          arr.findIndex(a => a.word === alt.word) === idx // Remove duplicates
        ),
        isEditable: unlockedWords.has(index),
        isEditing: editingWordIndex === index
      };
    });
  }, [text, wordConfidenceMap, redundancyAnalysis, unlockedWords, editingWordIndex]);

  const getConfidenceColor = useCallback((confidence: number) => {
    if (confidence >= 0.8) {
      return 'rgba(34, 197, 94, 0.2)'; // Green for high confidence
    } else if (confidence >= 0.5) {
      return 'rgba(234, 179, 8, 0.3)'; // Yellow for medium confidence
    } else {
      return 'rgba(239, 68, 68, 0.4)'; // Red for low confidence
    }
  }, []);

  const handleWordClick = useCallback((wordIndex: number, event: React.MouseEvent) => {
    const wordInfo = wordData[wordIndex];
    
    if (wordInfo.isEditable) {
      // Start editing if word is unlocked
      setEditingWordIndex(wordIndex);
      setEditingValue(wordInfo.word);
      setShowPopup(null);
    } else if (wordInfo.alternatives.length > 0 || wordInfo.confidence < 0.8) {
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
    onTextUpdate(newText);
    setShowPopup(null);
  }, [wordData, text, onTextUpdate]);

  const handleEditingComplete = useCallback((wordIndex: number, newValue: string) => {
    if (newValue.trim() !== '') {
      const newWords = [...wordData.map(w => w.word)];
      newWords[wordIndex] = newValue.trim();
      const newText = rebuildTextWithFormatting(text, newWords);
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
  const handleDocumentClick = useCallback((event: MouseEvent) => {
    const target = event.target as HTMLElement;
    if (!target.closest('.confidence-popup') && !target.closest('.confidence-word')) {
      setShowPopup(null);
    }
  }, []);

  React.useEffect(() => {
    document.addEventListener('click', handleDocumentClick);
    return () => document.removeEventListener('click', handleDocumentClick);
  }, [handleDocumentClick]);

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
                  onBlur={() => handleEditingComplete(currentWordIndex, editingValue)}
                  onKeyDown={(e) => handleKeyDown(e, currentWordIndex)}
                  className="word-edit-input"
                  autoFocus
                />
              );
            }

            return (
              <span
                key={`word-${segmentIndex}`}
                className={`confidence-word ${wordInfo.isEditable ? 'editable' : ''} ${
                  wordInfo.alternatives.length > 0 || wordInfo.confidence < 0.8 ? 'clickable' : ''
                }`}
                style={{
                  backgroundColor: getConfidenceColor(wordInfo.confidence),
                  cursor: wordInfo.isEditable ? 'text' : 
                         (wordInfo.alternatives.length > 0 || wordInfo.confidence < 0.8) ? 'pointer' : 'default'
                }}
                onClick={(e) => handleWordClick(currentWordIndex, e)}
                title={`Confidence: ${(wordInfo.confidence * 100).toFixed(0)}%${
                  wordInfo.alternatives.length > 0 ? ` • ${wordInfo.alternatives.length} alternatives` : ''
                }`}
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
            <div className="popup-header">
              <span className="popup-word">{wordData[showPopup]?.word}</span>
              <span className="popup-confidence">
                {((wordData[showPopup]?.confidence || 0) * 100).toFixed(0)}% confidence
              </span>
            </div>
            
            {wordData[showPopup]?.alternatives.length > 0 && (
              <div className="popup-alternatives">
                <div className="alternatives-label">Alternatives:</div>
                {wordData[showPopup].alternatives.map((alt, index) => (
                  <button
                    key={index}
                    className="alternative-option"
                    onClick={() => handleSelectAlternative(showPopup, alt.word)}
                  >
                    <span className="alt-word">{alt.word}</span>
                    <span className="alt-source">{alt.source}</span>
                  </button>
                ))}
              </div>
            )}
            
            <div className="popup-actions">
              <button
                className="unlock-button"
                onClick={() => handleUnlockWord(showPopup)}
              >
                🔓 Unlock for Editing
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}; 