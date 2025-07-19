export interface BoundingBoxSettings {
  enabled: boolean;
  complexity: 'simple' | 'standard' | 'enhanced';
  model: string;
}

export interface BoundingBoxResult {
  success: boolean;
  lines: Array<{
    line_index: number;
    bounds: { y1: number; y2: number; x1: number; x2: number };
    confidence: number;
  }>;
  words_by_line: Array<{
    line_index: number;
    line_bounds: { y1: number; y2: number; x1: number; x2: number };
    words: Array<{
      word: string;
      bounds: { x1: number; y1: number; x2: number; y2: number };
      confidence: number;
    }>;
    processing_time: number;
  }>;
  total_processing_time: number;
  total_words: number;
  error?: string;
}

export interface BoundingBoxState {
  enabled: boolean;
  isProcessing: boolean;
  boundingBoxResult: BoundingBoxResult | null;
  complexity: 'simple' | 'standard' | 'enhanced';
  model: string;
} 