import { useState, useCallback } from 'react';
import { BoundingBoxState, BoundingBoxResult, BoundingBoxSettings } from '../types/boundingBox';
import { runBoundingBoxPipeline } from '../services/boundingBoxApi';

export const useBoundingBoxState = () => {
  const [boundingBoxState, setBoundingBoxState] = useState<BoundingBoxState>({
    enabled: false,
    isProcessing: false,
    boundingBoxResult: null,
    complexity: 'standard',
    model: 'gpt-4o'
  });

  const updateSettings = useCallback((settings: Partial<BoundingBoxSettings>) => {
    setBoundingBoxState(prev => ({
      ...prev,
      ...settings
    }));
  }, []);

  const processBoundingBox = useCallback(async (file: File) => {
    if (!boundingBoxState.enabled) return null;

    setBoundingBoxState(prev => ({ ...prev, isProcessing: true }));

    try {
      const result = await runBoundingBoxPipeline(
        file,
        boundingBoxState.model,
        boundingBoxState.complexity
      );

      setBoundingBoxState(prev => ({
        ...prev,
        boundingBoxResult: result,
        isProcessing: false
      }));

      return result;
    } catch (error) {
      setBoundingBoxState(prev => ({
        ...prev,
        isProcessing: false,
        boundingBoxResult: {
          success: false,
          lines: [],
          words_by_line: [],
          total_processing_time: 0,
          total_words: 0,
          error: error instanceof Error ? error.message : 'Unknown error'
        }
      }));
      throw error;
    }
  }, [boundingBoxState.enabled, boundingBoxState.model, boundingBoxState.complexity]);

  const resetBoundingBoxState = useCallback(() => {
    setBoundingBoxState({
      enabled: false,
      isProcessing: false,
      boundingBoxResult: null,
      complexity: 'standard',
      model: 'gpt-4o'
    });
  }, []);

  return {
    boundingBoxState,
    updateSettings,
    processBoundingBox,
    resetBoundingBoxState
  };
}; 