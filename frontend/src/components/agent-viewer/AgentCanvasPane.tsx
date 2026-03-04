import React from 'react';
import type { AgentViewerEvent } from '../../services/agentViewerApi';
import type { DiffRow } from './canvas/types';
import type { AgentCanvasPage, CanvasPageOption } from './types';
import { AgentCanvasContent } from './AgentCanvasContent';

type Props = {
  currentEvent: AgentViewerEvent | null;
  canvasPageIndex: number;
  setCanvasPageIndex: React.Dispatch<React.SetStateAction<number>>;
  availableCanvasPages: CanvasPageOption[];
  activeCanvasPage: AgentCanvasPage;
  loadingArtifact: boolean;
  artifactError: string | null;
  selectedArtifactJson: any;
  transcriptionFallbackText: string;
  transcriptDiffRows: DiffRow[];
  activeImageUrl: string | null;
  verifyOriginalSize: [number, number];
  imageVerifyResults: Array<Record<string, any>>;
  selectedVerifyResultIndex: number;
  setSelectedVerifyResultIndex: React.Dispatch<React.SetStateAction<number>>;
  selectedVerifyResult: Record<string, any> | null;
  selectedVerifyMeta: Record<string, any> | null;
  previewPathD: string;
};

export function AgentCanvasPane({
  currentEvent,
  canvasPageIndex,
  setCanvasPageIndex,
  availableCanvasPages,
  activeCanvasPage,
  loadingArtifact,
  artifactError,
  selectedArtifactJson,
  transcriptionFallbackText,
  transcriptDiffRows,
  activeImageUrl,
  verifyOriginalSize,
  imageVerifyResults,
  selectedVerifyResultIndex,
  setSelectedVerifyResultIndex,
  selectedVerifyResult,
  selectedVerifyMeta,
  previewPathD,
}: Props) {
  return (
    <div style={{ position: 'absolute', inset: '12px 360px 78px 12px', borderRadius: 12, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(0,0,0,0.28)', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      <div style={{ padding: '6px 12px', borderBottom: '1px solid rgba(255,255,255,0.06)', display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        {currentEvent && (
          <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 999, background: 'rgba(142,197,255,0.15)', border: '1px solid rgba(142,197,255,0.25)' }}>
            {String(currentEvent.payload?.phase || currentEvent.status?.stage || 'idle').replace(/_/g, ' ')}
          </span>
        )}
        {typeof currentEvent?.iteration === 'number' && (
          <span style={{ fontSize: 10, opacity: 0.6 }}>iter {currentEvent.iteration}</span>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 6 }}>
          <button onClick={() => setCanvasPageIndex((v) => Math.max(0, v - 1))} disabled={canvasPageIndex <= 0} style={{ fontSize: 11, padding: '2px 8px' }}>◀</button>
          <span style={{ fontSize: 11, opacity: 0.84 }}>
            {availableCanvasPages[canvasPageIndex]?.label || 'Live Draft'}
          </span>
          <button onClick={() => setCanvasPageIndex((v) => Math.min(availableCanvasPages.length - 1, v + 1))} disabled={canvasPageIndex >= availableCanvasPages.length - 1} style={{ fontSize: 11, padding: '2px 8px' }}>▶</button>
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 14 }}>
        <AgentCanvasContent
          activeCanvasPage={activeCanvasPage}
          loadingArtifact={loadingArtifact}
          artifactError={artifactError}
          selectedArtifactJson={selectedArtifactJson}
          transcriptionFallbackText={transcriptionFallbackText}
          transcriptDiffRows={transcriptDiffRows}
          activeImageUrl={activeImageUrl}
          verifyOriginalSize={verifyOriginalSize}
          imageVerifyResults={imageVerifyResults}
          selectedVerifyResultIndex={selectedVerifyResultIndex}
          setSelectedVerifyResultIndex={setSelectedVerifyResultIndex}
          selectedVerifyResult={selectedVerifyResult}
          selectedVerifyMeta={selectedVerifyMeta}
          previewPathD={previewPathD}
        />
      </div>
    </div>
  );
}
