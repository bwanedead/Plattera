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
  // Backend actual property names
  total_positions_analyzed: number;
  total_differences_found: number;
  average_confidence_score: number;
  quality_assessment: string;
  confidence_distribution: {
    high: number;
    medium: number;
    low: number;
  };
  // Additional backend properties
  processing_time_seconds?: number;
  total_blocks_processed?: number;
  accuracy_percentage?: number;
  difference_categories?: Record<string, any>;
  alignment_method?: string;
  estimated_tcoffee_accuracy?: string;
}

export interface AlignmentToken {
  token: string;
  confidence: number;
  position: number;
  original_start: number;
  is_difference: boolean;
  alternatives?: string[];
}

export interface DraftAlignmentResult {
  aligned_tokens: AlignmentToken[];
  draft_id: string;
  original_to_alignment: number[];
}

export interface AlignmentResult {
  success: boolean;
  processing_time: number;
  summary: AlignmentSummary;
  consensus_text?: string;
  visualization_html?: string;
  per_draft_alignment_mapping?: Record<string, any>;
  confidence_results?: any;
  alignment_results?: any;
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

// --- Editable Draft Types ---

export interface EditOperation {
  id: string;
  timestamp: number;
  type: 'alternative_selection' | 'manual_edit';
  blockIndex: number;
  tokenIndex: number;
  originalValue: string;
  newValue: string;
  confidence?: number;
  alternatives?: string[];
}

export interface EditableDraftState {
  originalDraft: {
    content: string;
    blockTexts: string[];
  };
  editedDraft: {
    content: string;
    blockTexts: string[];
  };
  editHistory: EditOperation[];
  currentHistoryIndex: number;
  hasUnsavedChanges: boolean;
  // Track which draft the edits were made on
  editedFromDraft: number | 'consensus' | 'best' | null;
}

export interface TokenMapping {
  originalStart: number;
  originalEnd: number;
  alignedIndex: number;
  originalText: string;
  cleanedText: string;
} 