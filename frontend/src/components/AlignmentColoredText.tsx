import React, { useMemo } from 'react';

interface AlignmentColoredTextProps {
  text: string;
  heatmapData?: {
    original_to_alignment: number[];
    confidence_scores: number[];
  } | null;
  isAlignmentMode: boolean;
}

export const AlignmentColoredText: React.FC<AlignmentColoredTextProps> = ({
  text,
  heatmapData,
  isAlignmentMode
}) => {
  console.log('AlignmentColoredText heatmapData', {
    isAlignmentMode,
    heatmapData,
    text,
  });

  // If not in alignment mode or no heatmap data, render plain text
  if (!isAlignmentMode || !heatmapData || !heatmapData.original_to_alignment || !heatmapData.confidence_scores) {
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

  // For each word in the text, use its index to look up the alignment position and get the confidence score
  const getWordConfidence = (tokenIdx: number): 'high' | 'medium' | 'low' => {
    const alignPos = heatmapData.original_to_alignment[tokenIdx];
    if (typeof alignPos !== 'number') return 'high';
    const score = heatmapData.confidence_scores[alignPos];
    if (typeof score !== 'number') return 'high';
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
        {(() => {
          // Flatten all words in the text into a single array, keeping track of their original token index
          const lines = text.split('\n');
          let globalTokenIdx = 0;
          return lines.map((line, lineIndex) => {
            if (/^─+$/.test(line.trim())) {
              return <hr key={lineIndex} className="section-divider" />;
            }
            if (!line.trim()) {
              return <div key={lineIndex} className="line-break" />;
            }
            const words = line.split(/(\s+)/);
            return (
              <p key={lineIndex} className="colored-text-line">
                {words.map((word, wordIndex) => {
                  if (!word.trim()) {
                    return <span key={wordIndex}>{word}</span>;
                  }
                  const confidence = getWordConfidence(globalTokenIdx);
                  const el = (
                    <span
                      key={wordIndex}
                      className={`confidence-word ${confidence}`}
                      title={`Confidence: ${confidence}`}
                    >
                      {word}
                    </span>
                  );
                  globalTokenIdx++;
                  return el;
                })}
              </p>
            );
          });
        })()}
      </div>
    </div>
  );
};