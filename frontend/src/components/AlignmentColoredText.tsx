import React from 'react';

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
  // If not in alignment mode, show regular text
  if (!isAlignmentMode || !confidenceData) {
    return (
      <div className="formatted-text-display">
        {text.split('\n').map((line: string, index: number) => {
          if (/^─+$/.test(line.trim())) {
            return <hr key={index} className="section-divider" />
          }
          if (!line.trim()) {
            return <div key={index} className="line-break" />
          }
          return <p key={index} className="text-line">{line}</p>
        })}
      </div>
    );
  }

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
        {text.split('\n').map((line: string, lineIndex: number) => {
          if (/^─+$/.test(line.trim())) {
            return <hr key={lineIndex} className="section-divider" />
          }
          if (!line.trim()) {
            return <div key={lineIndex} className="line-break" />
          }
          
          // Color-code words in this line
          const lineWords = line.split(/(\s+)/);
          return (
            <p key={lineIndex} className="colored-text-line">
              {lineWords.map((word, wordIndex) => {
                if (!word.trim()) {
                  return <span key={wordIndex}>{word}</span>;
                }
                
                // Replace the demo confidence logic with real alignment data
                const getWordConfidence = (word: string, wordIndex: number, lineIndex: number): 'high' | 'medium' | 'low' => {
                  if (!confidenceData || !confidenceData.blocks) {
                    return 'high'; // Default when no data
                  }
                  
                  // Get confidence from actual alignment results
                  const blockData = confidenceData.blocks?.['legal_text'];
                  if (blockData && blockData.confidence_scores) {
                    // Calculate absolute position from line and word indices
                    const absolutePosition = lineIndex * 10 + wordIndex; // Approximate
                    
                    if (absolutePosition < blockData.confidence_scores.length) {
                      const confidence = blockData.confidence_scores[absolutePosition];
                      if (confidence >= 0.8) return 'high';
                      if (confidence >= 0.5) return 'medium';
                      return 'low';
                    }
                  }
                  
                  // Fallback: use word characteristics for demo
                  if (word.length < 3) return 'medium';
                  if (/[0-9]/.test(word)) return 'low';
                  if (/[A-Z]{2,}/.test(word)) return 'medium';
                  return 'high';
                };
                
                const confidence = getWordConfidence(word, wordIndex, lineIndex);
                
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