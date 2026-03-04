import React from 'react';
import type { DiffRow } from './types';

type Props = {
  transcriptDiffRows: DiffRow[];
};

export function DiffCanvasPage({ transcriptDiffRows }: Props) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
      <div>
        <div style={{ fontSize: 11, opacity: 0.75, marginBottom: 6 }}>Source</div>
        <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, overflow: 'hidden' }}>
          {transcriptDiffRows.slice(0, 300).map((row, idx) => (
            <div key={`l-${idx}`} style={{ padding: '3px 8px', fontSize: 11, lineHeight: 1.35, background: row.changed ? 'rgba(255,107,107,0.10)' : 'transparent' }}>
              {row.left || ' '}
            </div>
          ))}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 11, opacity: 0.75, marginBottom: 6 }}>Edited</div>
        <div style={{ border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, overflow: 'hidden' }}>
          {transcriptDiffRows.slice(0, 300).map((row, idx) => (
            <div key={`r-${idx}`} style={{ padding: '3px 8px', fontSize: 11, lineHeight: 1.35, background: row.changed ? 'rgba(42,196,119,0.14)' : 'transparent' }}>
              {row.right || ' '}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

