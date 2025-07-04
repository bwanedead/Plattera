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

// --- Alignment Engine Types ---

export interface AlignmentDraft {
  draft_id: string;
  blocks: Array<{
    id: string;
    text: string;
  }>;
}

export interface AlignmentSummary {
  total_positions: number;
  total_differences: number;
  average_confidence: number;
  quality_assessment: string;
  high_confidence_positions: number;
  medium_confidence_positions: number;
  low_confidence_positions: number;
}

export interface AlignmentResult {
  success: boolean;
  processing_time: number;
  summary: AlignmentSummary;
  consensus_text?: string;
  visualization_html?: string;
  per_draft_alignment_mapping?: Record<string, any>;
  error?: string;
}

export interface AlignmentState {
  isAligning: boolean;
  alignmentResult: AlignmentResult | null;
  showHeatmap: boolean;
  showAlignmentPanel: boolean;
}

export interface ConfidenceWord {
  text: string;
  confidence: number;
  position: number;
  alternatives?: string[];
  isClickable: boolean;
} 