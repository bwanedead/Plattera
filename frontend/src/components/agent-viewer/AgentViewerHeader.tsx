import React from 'react';
import type { CanvasMode, ViewerTheme } from './types';

type Props = {
  theme: ViewerTheme;
  setTheme: React.Dispatch<React.SetStateAction<ViewerTheme>>;
  canvasMode: CanvasMode;
  setCanvasMode: React.Dispatch<React.SetStateAction<CanvasMode>>;
  hasActiveRun: boolean;
  activeLoopKind: string | null;
  activeRunId: string | null;
  connected: boolean;
  isTranscribing: boolean;
  layerChips: {
    layer1: string;
    layer2: string;
    layer3: string;
    closureState: string;
    unresolvedCount: number;
  } | null;
  onClose: () => void;
};

export function AgentViewerHeader({
  theme,
  setTheme,
  canvasMode,
  setCanvasMode,
  hasActiveRun,
  activeLoopKind,
  activeRunId,
  connected,
  isTranscribing,
  layerChips,
  onClose,
}: Props) {
  const chipStyle = (value: string): React.CSSProperties => {
    const v = String(value || '').toLowerCase();
    const bg = v === 'satisfied' || v === 'achieved'
      ? 'rgba(42,196,119,0.20)'
      : v === 'blocked' || v === 'failed'
      ? 'rgba(255,107,107,0.20)'
      : v === 'in_progress' || v === 'running'
      ? 'rgba(142,197,255,0.20)'
      : 'rgba(255,255,255,0.1)';
    return {
      fontSize: 10,
      lineHeight: 1.1,
      padding: '2px 7px',
      borderRadius: 999,
      border: '1px solid rgba(255,255,255,0.22)',
      background: bg,
      opacity: 0.95,
    };
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 12px',
        borderBottom: '1px solid rgba(255,255,255,0.08)',
        background: theme === 'space'
          ? 'linear-gradient(180deg, rgba(8,12,22,0.95), rgba(2,2,2,0.98))'
          : '#020202',
        zIndex: 1,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <strong style={{ fontSize: 13 }}>Agent Viewer</strong>
        <button onClick={() => setTheme((t) => (t === 'void' ? 'space' : 'void'))} style={{ fontSize: 11, borderRadius: 999, padding: '3px 8px' }}>
          Theme: {theme === 'void' ? 'Void' : 'Space'}
        </button>
        <button onClick={() => setCanvasMode('transcription')} style={{ fontSize: 11, borderRadius: 999, padding: '3px 8px', opacity: canvasMode === 'transcription' ? 1 : 0.72 }}>
          Transcription
        </button>
        <button onClick={() => setCanvasMode('agent')} disabled={!hasActiveRun} style={{ fontSize: 11, borderRadius: 999, padding: '3px 8px', opacity: canvasMode === 'agent' ? 1 : 0.72 }}>
          Agent
        </button>
        <span style={{ fontSize: 11, opacity: 0.8 }}>{activeLoopKind ?? 'idle'}</span>
        <span style={{ fontSize: 11, opacity: 0.72 }}>{activeRunId ?? 'no active run'}</span>
        {layerChips && (
          <>
            <span style={chipStyle(layerChips.layer1)}>L1 {layerChips.layer1}</span>
            <span style={chipStyle(layerChips.layer2)}>L2 {layerChips.layer2}</span>
            <span style={chipStyle(layerChips.layer3)}>L3 {layerChips.layer3}</span>
            <span style={chipStyle(layerChips.closureState)}>Closure {layerChips.closureState}</span>
            <span style={{ ...chipStyle(layerChips.unresolvedCount > 0 ? 'blocked' : 'satisfied') }}>
              Open {layerChips.unresolvedCount}
            </span>
          </>
        )}
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 8, height: 8, borderRadius: 999, background: connected ? '#2ac477' : '#d4a83f' }} />
        <span style={{ fontSize: 11, opacity: 0.82 }}>{hasActiveRun ? (connected ? 'Live' : 'Disconnected') : (isTranscribing ? 'Transcribing' : 'Idle')}</span>
        <button
          onClick={onClose}
          aria-label="Close Agent Viewer"
          title="Close"
          style={{ width: 30, height: 30, borderRadius: 999, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, lineHeight: 1, fontWeight: 600, padding: 0 }}
        >
          ×
        </button>
      </div>
    </div>
  );
}
