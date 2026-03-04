import React from 'react';

type TranscriptionDraft = { id: string; label: string; text: string };

type Props = {
  transcriptionDrafts: TranscriptionDraft[];
  selectedDraftIndex: number;
  setSelectedDraftIndex: React.Dispatch<React.SetStateAction<number>>;
  isTranscribing: boolean;
};

export function TranscriptionCanvasPane({
  transcriptionDrafts,
  selectedDraftIndex,
  setSelectedDraftIndex,
  isTranscribing,
}: Props) {
  if (transcriptionDrafts.length === 0) {
    return (
      <div style={{ minHeight: 0, padding: 14, display: 'flex', flexDirection: 'column', gap: 12, zIndex: 1 }}>
        <div style={{ flex: 1, border: '1px solid rgba(255,255,255,0.08)', borderRadius: 10, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 10, background: 'rgba(255,255,255,0.01)' }}>
          <div style={{ fontSize: 13, opacity: 0.86 }}>{isTranscribing ? 'Waiting for transcription drafts…' : 'No transcription artifact loaded yet.'}</div>
          <div style={{ fontSize: 11, opacity: 0.68 }}>Keep this viewer open. Drafts will appear here as they complete.</div>
        </div>
      </div>
    );
  }

  return (
    <div style={{ minHeight: 0, padding: 14, display: 'flex', flexDirection: 'column', gap: 12, zIndex: 1 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ fontSize: 12, opacity: 0.8 }}>Draft {selectedDraftIndex + 1} of {transcriptionDrafts.length}</div>
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => setSelectedDraftIndex((v) => Math.max(0, v - 1))} disabled={selectedDraftIndex <= 0}>◀</button>
          <button onClick={() => setSelectedDraftIndex((v) => Math.min(transcriptionDrafts.length - 1, v + 1))} disabled={selectedDraftIndex >= transcriptionDrafts.length - 1}>▶</button>
        </div>
      </div>
      <div style={{ fontSize: 12, opacity: 0.85, padding: '8px 10px', borderRadius: 8, border: '1px solid rgba(255,255,255,0.08)', background: 'rgba(255,255,255,0.01)' }}>
        {transcriptionDrafts[selectedDraftIndex]?.label || `Draft ${selectedDraftIndex + 1}`}
      </div>
      <pre style={{ margin: 0, flex: 1, minHeight: 0, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.45, padding: 12, borderRadius: 10, border: '1px solid rgba(255,255,255,0.09)', background: 'rgba(255,255,255,0.015)' }}>
        {transcriptionDrafts[selectedDraftIndex]?.text || ''}
      </pre>
    </div>
  );
}

