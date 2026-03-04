import React from 'react';
import { readableArtifactText } from '../agentViewerUtils';

type Props = {
  selectedArtifactJson: any;
};

export function OpsChecksCanvasPage({ selectedArtifactJson }: Props) {
  return (
    <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-word', fontSize: 12, lineHeight: 1.4 }}>
      {readableArtifactText(selectedArtifactJson)}
    </pre>
  );
}

