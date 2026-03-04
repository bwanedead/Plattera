import type React from 'react';
import type { AgentCanvasPage } from '../types';

export type DiffRow = { left: string; right: string; changed: boolean };

export type AgentCanvasContentProps = {
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
