import { BoundingBoxResult } from '../types/boundingBox';

const API_BASE_URL = 'http://localhost:8000/api';

export const detectLinesAPI = async (file: File): Promise<any> => {
  const formData = new FormData();
  formData.append('image', file);

  const response = await fetch(`${API_BASE_URL}/bounding-boxes/detect-lines`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Line detection failed: ${response.statusText}`);
  }

  return response.json();
};

export const detectWordsAPI = async (file: File, lines: any[]): Promise<any> => {
  const formData = new FormData();
  formData.append('image', file);
  formData.append('lines', JSON.stringify(lines));

  const response = await fetch(`${API_BASE_URL}/bounding-boxes/detect-words`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Word detection failed: ${response.statusText}`);
  }

  return response.json();
};

export const runBoundingBoxPipeline = async (
  file: File,
  model: string,
  complexity: string
): Promise<BoundingBoxResult> => {
  try {
    // Stage 1: Line detection
    const lineResult = await detectLinesAPI(file);
    
    if (!lineResult.success) {
      throw new Error(lineResult.error || 'Line detection failed');
    }

    // Stage 2: Word segmentation
    const wordResult = await detectWordsAPI(file, lineResult.lines);
    
    if (!wordResult.success) {
      throw new Error(wordResult.error || 'Word detection failed');
    }

    // Combine results
    return {
      success: true,
      lines: lineResult.lines,
      words_by_line: wordResult.words_by_line,
      total_processing_time: lineResult.processing_time + wordResult.processing_time,
      total_words: wordResult.total_words
    };
  } catch (error) {
    return {
      success: false,
      lines: [],
      words_by_line: [],
      total_processing_time: 0,
      total_words: 0,
      error: error instanceof Error ? error.message : 'Unknown error'
    };
  }
};

export const getBoundingBoxStatusAPI = async (): Promise<any> => {
  const response = await fetch(`${API_BASE_URL}/bounding-boxes/status`);
  
  if (!response.ok) {
    throw new Error(`Status check failed: ${response.statusText}`);
  }

  return response.json();
}; 