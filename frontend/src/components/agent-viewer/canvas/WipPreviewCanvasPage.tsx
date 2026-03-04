import React from 'react';

type Props = {
  previewPathD: string;
};

export function WipPreviewCanvasPage({ previewPathD }: Props) {
  return (
    <div style={{ height: '100%', display: 'grid', placeItems: 'center' }}>
      {previewPathD ? (
        <svg viewBox="0 0 1000 1000" style={{ width: '100%', height: '100%', maxHeight: 560, borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.02)' }}>
          <path d={previewPathD} fill="rgba(142,197,255,0.18)" stroke="#8ec5ff" strokeWidth={4} />
        </svg>
      ) : (
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 14, opacity: 0.9 }}>Constructing geometry preview…</div>
          <div style={{ fontSize: 11, opacity: 0.7, marginTop: 6 }}>Work-in-progress view can display incomplete geometry states.</div>
        </div>
      )}
    </div>
  );
}

