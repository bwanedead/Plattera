// --- Type Definitions for the Image Processing Workspace ---

export interface EnhancementSettings {
  contrast: number;
  sharpness: number;
  brightness: number;
  color: number;
}

export interface RedundancySettings {
  enabled: boolean;
  count: number;
  consensusStrategy: string;
}

export interface ProcessingResult {
  input: string;
  status: 'completed' | 'error';
  result: {
    extracted_text: string;
    metadata: any;
  } | null;
  error?: string;
} 