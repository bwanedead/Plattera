import React, { useMemo } from 'react';

interface AlignmentColoredTextProps {
  text: string;
  confidenceData: any;
  isAlignmentMode: boolean;
}

export const AlignmentColoredText: React.FC<AlignmentColoredTextProps> = ({
  text,
  confidenceData,
  isAlignmentMode
}) => {
  // Memoize the token-to-confidence mapping to avoid recalculating on every render
  const tokenConfidenceMap = useMemo(() => {
    if (!isAlignmentMode || !confidenceData || !confidenceData.blocks) {
      return new Map();
    }

    const map = new Map<string, number>();
    // Assume single block for now, this can be made more robust
    const blockKey = Object.keys(confidenceData.blocks)[0];
    if (!blockKey) return map;

    const block = confidenceData.blocks[blockKey];
    if (!block || !block.tokens || !block.confidence_scores) {
      return map;
    }

    // Create a map of token -> confidence score
    for (let i = 0; i < block.tokens.length; i++) {
      const token = block.tokens[i];
      const score = block.confidence_scores[i];
      if (token && typeof score === 'number') {
        // Handle cases where the same token appears multiple times with different scores
        // For simplicity, we'll just take the first score we see for a given token.
        if (!map.has(token.toLowerCase())) {
          map.set(token.toLowerCase(), score);
        }
      }
    }
    return map;
  }, [confidenceData, isAlignmentMode]);

  console.log('AlignmentColoredText', {
    isAlignmentMode,
    confidenceData,
    tokenConfidenceMapSize: tokenConfidenceMap.size,
    text,
  });

  if (!isAlignmentMode || tokenConfidenceMap.size === 0) {
    return (
      <div className="formatted-text-display">
        {text.split('\n').map((line, index) => {
          if (/^─+$/.test(line.trim())) {
            return <hr key={index} className="section-divider" />;
          }
          if (!line.trim()) {
            return <div key={index} className="line-break" />;
          }
          return <p key={index} className="text-line">{line}</p>;
        })}
      </div>
    );
  }

  const getWordConfidence = (word: string): 'high' | 'medium' | 'low' => {
    const score = tokenConfidenceMap.get(word.toLowerCase().replace(/[.,/#!$%^&*;:{}=\-_`~()]/g,""));
    if (typeof score !== 'number') {
      return 'high'; // Default for words not in the map (e.g., punctuation)
    }
    if (score >= 0.8) return 'high';
    if (score >= 0.5) return 'medium';
    return 'low';
  };

  return (
    <div className="alignment-colored-text">
      <div className="confidence-legend-inline">
        <span className="legend-item">
          <span className="confidence-indicator high"></span>High Confidence
        </span>
        <span className="legend-item">
          <span className="confidence-indicator medium"></span>Medium Confidence  
        </span>
        <span className="legend-item">
          <span className="confidence-indicator low"></span>Low Confidence
        </span>
      </div>
      
      <div className="colored-text-content">
        {text.split('\n').map((line, lineIndex) => {
          if (/^─+$/.test(line.trim())) {
            return <hr key={lineIndex} className="section-divider" />;
          }
          if (!line.trim()) {
            return <div key={lineIndex} className="line-break" />;
          }
          
          return (
            <p key={lineIndex} className="colored-text-line">
              {line.split(/(\s+)/).map((word, wordIndex) => {
                if (!word.trim()) {
                  return <span key={wordIndex}>{word}</span>;
                }
                
                const confidence = getWordConfidence(word);
                
                return (
                  <span 
                    key={wordIndex} 
                    className={`confidence-word ${confidence}`}
                    title={`Confidence: ${confidence}`}
                  >
                    {word}
                  </span>
                );
              })}
            </p>
          );
        })}
      </div>
    </div>
  );
};