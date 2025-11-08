import React from 'react';

interface FinalTextEditorProps {
  sections: string[];
  onChange: (index: number, value: string) => void;
  onSave: (index: number) => void;
  onDone?: () => void;
}

export const FinalTextEditor: React.FC<FinalTextEditorProps> = ({ sections, onChange, onSave, onDone }) => {
  const isSingle = Array.isArray(sections) && sections.length <= 1;
  return (
    <div className="final-text-editor" style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        {onDone && <button className="mode-button" onClick={onDone}>Done</button>}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        {sections.map((blk, i) => (
          <div key={i} className="stitched-block" style={{ marginBottom: 16 }}>
            <textarea
              value={blk}
              onChange={(e) => onChange(i, e.target.value)}
              rows={isSingle ? 28 : Math.max(12, Math.min(40, (blk.match(/\n/g)?.length || 0) + 2))}
              className="final-section-textarea"
              style={{ width: '100%', height: isSingle ? '100%' : undefined, overflow: 'auto' }}
            />
            <div style={{ marginTop: 8 }}>
              <button className="mode-button" onClick={() => onSave(i)}>Save Section</button>
            </div>
            <div style={{ margin: '10px 0 16px', opacity: 0.5 }}>
              <hr style={{ border: 0, borderTop: '1px dashed #444' }} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};


