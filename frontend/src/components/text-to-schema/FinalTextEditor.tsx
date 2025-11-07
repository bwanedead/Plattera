import React from 'react';

interface FinalTextEditorProps {
  sections: string[];
  onChange: (index: number, value: string) => void;
  onSave: (index: number) => void;
}

export const FinalTextEditor: React.FC<FinalTextEditorProps> = ({ sections, onChange, onSave }) => {
  return (
    <div className="final-text-editor">
      {sections.map((blk, i) => (
        <div key={i} className="stitched-block">
          <textarea
            value={blk}
            onChange={(e) => onChange(i, e.target.value)}
            rows={Math.max(6, Math.min(20, (blk.match(/\n/g)?.length || 0) + 2))}
            className="final-section-textarea"
            style={{ width: '100%' }}
          />
          <div style={{ marginTop: 8 }}>
            <button onClick={() => onSave(i)}>Save Section</button>
          </div>
          <div style={{ margin: '10px 0 16px', opacity: 0.5 }}>
            <hr style={{ border: 0, borderTop: '1px dashed #444' }} />
          </div>
        </div>
      ))}
    </div>
  );
};


