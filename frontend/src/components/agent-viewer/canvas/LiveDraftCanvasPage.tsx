import React from 'react';
import { transcriptTextFromArtifact } from '../agentViewerUtils';

type Props = {
  loadingArtifact: boolean;
  artifactError: string | null;
  selectedArtifactJson: any;
  transcriptionFallbackText: string;
};

export function LiveDraftCanvasPage({
  loadingArtifact,
  artifactError,
  selectedArtifactJson,
  transcriptionFallbackText,
}: Props) {
  return (
    <>
      {loadingArtifact && <div style={{ fontSize: 12, opacity: 0.86 }}>Loading latest artifact…</div>}
      {artifactError && <div style={{ fontSize: 12, color: '#ff9aa0' }}>{artifactError}</div>}
      {!loadingArtifact && !artifactError && !selectedArtifactJson && (
        <div style={{ fontSize: 12, opacity: 0.72 }}>No artifact loaded yet. Waiting for agent outputs…</div>
      )}
      {!loadingArtifact && !selectedArtifactJson && transcriptionFallbackText && (
        <div style={{ marginTop: 10 }}>
          <div style={{ fontSize: 11, opacity: 0.72, marginBottom: 6 }}>Fallback view: latest transcription draft</div>
          <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
            {transcriptionFallbackText}
          </pre>
        </div>
      )}
      {!loadingArtifact && !artifactError && selectedArtifactJson && (
        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
          {transcriptTextFromArtifact(selectedArtifactJson)}
        </pre>
      )}
    </>
  );
}

