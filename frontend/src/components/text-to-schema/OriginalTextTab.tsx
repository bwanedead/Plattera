import React from 'react';
import { CopyButton } from '../CopyButton';

interface OriginalTextTabProps {
  text: string;
  showSectionMarkers?: boolean;
  sections?: string[];
}

export const OriginalTextTab: React.FC<OriginalTextTabProps> = ({ text, showSectionMarkers = false, sections }) => {
  // If dossier section blocks are provided, display them with explicit dividers.
  const blocks = Array.isArray(sections) && sections.length > 0
    ? sections
    : (showSectionMarkers ? text.split(/\n{2,}/g) : [text]);
  return (
    <div className="original-text-tab">
      <div className="tab-header">
        <h4>Original Text</h4>
        <CopyButton
          onCopy={() => navigator.clipboard.writeText(text)}
          title="Copy original text"
        />
      </div>
      <div className="text-content">
        {showSectionMarkers ? (
          <div className="stitched-text">
            {blocks.map((blk, idx) => (
              <div key={idx} className="stitched-block">
                <pre className="original-text">{blk}</pre>
                {idx < blocks.length - 1 && (
                  <div className="stitched-separator" style={{ margin: '10px 0 16px', opacity: 0.5 }}>
                    <hr style={{ border: 0, borderTop: '1px dashed #444' }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <pre className="original-text">{text}</pre>
        )}
      </div>
    </div>
  );
}; 