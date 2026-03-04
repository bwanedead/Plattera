import React from 'react';
import { renderMetaOf } from '../agentViewerUtils';

type Props = {
  activeImageUrl: string | null;
  verifyOriginalSize: [number, number];
  imageVerifyResults: Array<Record<string, any>>;
  selectedVerifyResultIndex: number;
  setSelectedVerifyResultIndex: React.Dispatch<React.SetStateAction<number>>;
  selectedVerifyResult: Record<string, any> | null;
  selectedVerifyMeta: Record<string, any> | null;
};

export function ImageVerifyCanvasPage({
  activeImageUrl,
  verifyOriginalSize,
  imageVerifyResults,
  selectedVerifyResultIndex,
  setSelectedVerifyResultIndex,
  selectedVerifyResult,
  selectedVerifyMeta,
}: Props) {
  const clampedIndex = Math.min(selectedVerifyResultIndex, Math.max(imageVerifyResults.length - 1, 0));
  return (
    <div style={{ display: 'grid', gridTemplateRows: '1fr auto', height: '100%', gap: 10 }}>
      {activeImageUrl ? (
        <div style={{ borderRadius: 8, border: '1px solid rgba(255,255,255,0.12)', background: 'rgba(255,255,255,0.02)', overflow: 'hidden' }}>
          <svg viewBox={`0 0 ${verifyOriginalSize[0]} ${verifyOriginalSize[1]}`} style={{ width: '100%', maxHeight: 520 }}>
            <image href={activeImageUrl} x={0} y={0} width={verifyOriginalSize[0]} height={verifyOriginalSize[1]} preserveAspectRatio="xMidYMid meet" />
            {imageVerifyResults.map((result, idx) => {
              const meta = renderMetaOf(result);
              const crop = meta?.crop_box;
              if (!crop || typeof crop !== 'object') return null;
              const isSelected = idx === clampedIndex;
              const st = String(result?.status || '').toLowerCase();
              const stroke = st === 'match' || st === 'confirmed' ? '#2ac477' : st === 'mismatch' || st === 'rejected' ? '#ff6b6b' : '#d4a83f';
              return (
                <g key={`crop-${idx}`}>
                  <rect
                    x={Number(crop.x) || 0}
                    y={Number(crop.y) || 0}
                    width={Math.max(1, Number(crop.width) || 0)}
                    height={Math.max(1, Number(crop.height) || 0)}
                    fill={isSelected ? `${stroke}22` : `${stroke}12`}
                    stroke={stroke}
                    strokeWidth={isSelected ? 3 : 1.5}
                  />
                </g>
              );
            })}
          </svg>
        </div>
      ) : (
        <div style={{ fontSize: 12, opacity: 0.72 }}>No active image verification artifact yet.</div>
      )}
      <div style={{ display: 'grid', gap: 8 }}>
        {imageVerifyResults.length > 0 && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {imageVerifyResults.map((result, idx) => {
              const st = String(result?.status || '').toLowerCase();
              const active = idx === clampedIndex;
              const bg = st === 'match' || st === 'confirmed' ? 'rgba(42,196,119,0.2)' : st === 'mismatch' || st === 'rejected' ? 'rgba(255,107,107,0.2)' : 'rgba(212,168,63,0.2)';
              return (
                <button
                  key={`check-${idx}`}
                  onClick={() => setSelectedVerifyResultIndex(idx)}
                  style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: active ? bg : 'rgba(255,255,255,0.04)', border: active ? '1px solid rgba(255,255,255,0.4)' : '1px solid rgba(255,255,255,0.18)' }}
                >
                  {String(result?.check_id || `check_${idx + 1}`)}
                </button>
              );
            })}
          </div>
        )}
        {selectedVerifyResult && (
          <div style={{ fontSize: 11, opacity: 0.82, lineHeight: 1.4 }}>
            <div>Status: {String(selectedVerifyResult.status || 'unknown')}</div>
            <div>Observed: {String(selectedVerifyResult.observed_text || '').slice(0, 180)}</div>
            {selectedVerifyMeta?.crop_box && (
              <div>
                Crop: x={Number(selectedVerifyMeta.crop_box.x) || 0}, y={Number(selectedVerifyMeta.crop_box.y) || 0}, w={Number(selectedVerifyMeta.crop_box.width) || 0}, h={Number(selectedVerifyMeta.crop_box.height) || 0}
              </div>
            )}
            {selectedVerifyMeta?.zoom_factor && <div>Zoom: {String(selectedVerifyMeta.zoom_factor)}x</div>}
          </div>
        )}
        <div style={{ fontSize: 11, opacity: 0.75 }}>
          Showing current image used for verification with per-check crop overlays when available.
        </div>
      </div>
    </div>
  );
}

