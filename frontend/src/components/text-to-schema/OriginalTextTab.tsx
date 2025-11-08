import React from 'react';
import { CopyButton } from '../CopyButton';

interface OriginalTextTabProps {
  text: string;
  showSectionMarkers?: boolean;
  sections?: string[];
  onToggleEdit?: () => void;
  editMode?: boolean;
}

export const OriginalTextTab: React.FC<OriginalTextTabProps> = ({ text, showSectionMarkers = false, sections, onToggleEdit, editMode }) => {
  // If dossier section blocks are provided, display them with explicit dividers.
  const blocks = Array.isArray(sections) && sections.length > 0
    ? sections
    : (showSectionMarkers ? text.split(/\n{2,}/g) : [text]);
  return (
    <div className="original-text-tab">
      <div className="tab-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h4 style={{ margin: 0 }}>Original Text</h4>
        <div style={{ display: 'flex', gap: 8 }}>
          <CopyButton
            onCopy={() => navigator.clipboard.writeText(text)}
            title="Copy original text"
          />
          {onToggleEdit && (
            <button onClick={onToggleEdit} className="mode-button">
              {editMode ? 'Done' : 'Edit'}
            </button>
          )}
        </div>
      </div>
      <div className="text-content">
        {showSectionMarkers ? (
          <div className="stitched-text">
            {blocks.map((blk, idx) => (
              <div key={idx} className="stitched-block">
                <pre className="original-text" style={{ margin: 0, minHeight: 0 }}>{blk}</pre>
                {idx < blocks.length - 1 && (
                  <div className="stitched-separator" style={{ margin: '10px 0 16px', opacity: 0.5 }}>
                    <hr style={{ border: 0, borderTop: '1px dashed #444' }} />
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <pre className="original-text" style={{ margin: 0, minHeight: 0 }}>{text}</pre>
        )}
      </div>
    </div>
  );
}; 