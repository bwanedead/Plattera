import React from 'react';
import { DiffCanvasPage } from './canvas/DiffCanvasPage';
import { ImageVerifyCanvasPage } from './canvas/ImageVerifyCanvasPage';
import { LiveDraftCanvasPage } from './canvas/LiveDraftCanvasPage';
import { OpsChecksCanvasPage } from './canvas/OpsChecksCanvasPage';
import type { AgentCanvasContentProps } from './canvas/types';
import { WipPreviewCanvasPage } from './canvas/WipPreviewCanvasPage';

export function AgentCanvasContent(props: AgentCanvasContentProps) {
  const {
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
  } = props;

  if (activeCanvasPage === 'live_draft') {
    return (
      <LiveDraftCanvasPage
        loadingArtifact={loadingArtifact}
        artifactError={artifactError}
        selectedArtifactJson={selectedArtifactJson}
        transcriptionFallbackText={transcriptionFallbackText}
      />
    );
  }
  if (activeCanvasPage === 'diff') {
    return <DiffCanvasPage transcriptDiffRows={transcriptDiffRows} />;
  }
  if (activeCanvasPage === 'verify_image') {
    return (
      <ImageVerifyCanvasPage
        activeImageUrl={activeImageUrl}
        verifyOriginalSize={verifyOriginalSize}
        imageVerifyResults={imageVerifyResults}
        selectedVerifyResultIndex={selectedVerifyResultIndex}
        setSelectedVerifyResultIndex={setSelectedVerifyResultIndex}
        selectedVerifyResult={selectedVerifyResult}
        selectedVerifyMeta={selectedVerifyMeta}
      />
    );
  }
  if (activeCanvasPage === 'ops') {
    return <OpsChecksCanvasPage selectedArtifactJson={selectedArtifactJson} />;
  }
  return <WipPreviewCanvasPage previewPathD={previewPathD} />;
}

