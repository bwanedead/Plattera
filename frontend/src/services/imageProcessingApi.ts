import { EnhancementSettings, ProcessingResult, RedundancySettings, AlignmentDraft, AlignmentResult } from '../types/imageProcessing';

// --- API Calls for Image Processing Feature ---

export const processFilesAPI = async (files: File[], model: string, mode: string, enhancementSettings: EnhancementSettings, redundancySettings: RedundancySettings): Promise<ProcessingResult[]> => {
  console.log(`Processing ${files.length} files with model: ${model} and mode: ${mode}`);
  
  const results: ProcessingResult[] = [];
  
  for (const file of files) {
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('content_type', 'image-to-text');
      formData.append('extraction_mode', mode);
      formData.append('model', model);
      formData.append('cleanup_after', 'true');
      
      // Add enhancement settings
      formData.append('contrast', enhancementSettings.contrast.toString());
      formData.append('sharpness', enhancementSettings.sharpness.toString());
      formData.append('brightness', enhancementSettings.brightness.toString());
      formData.append('color', enhancementSettings.color.toString());
      
      // Add redundancy setting
      formData.append('redundancy', redundancySettings.enabled ? redundancySettings.count.toString() : '1');
      
      // Consensus strategy (only relevant when redundancy is enabled)
      if (redundancySettings.enabled) {
        formData.append('consensus_strategy', redundancySettings.consensusStrategy);
      }

      const response = await fetch('http://localhost:8000/api/process', {
        method: 'POST',
        body: formData
      });

      const data = await response.json();

      console.log("API response data:", data);

      if (data.status === 'success') {
        results.push({
          input: file.name,
          status: 'completed' as const,
          result: {
            extracted_text: data.extracted_text,
            metadata: { ...data.metadata }
          }
        });
      } else {
        results.push({
          input: file.name,
          status: 'error' as const,
          result: null,
          error: data.error || 'Processing failed'
        });
      }
    } catch (error) {
      results.push({
        input: file.name,
        status: 'error' as const,
        result: null,
        error: error instanceof Error ? error.message : 'Unknown error'
      });
    }
  }
  
  return results;
};

export const fetchModelsAPI = async () => {
  try {
    const response = await fetch('http://localhost:8000/api/models');
    
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    
    const data = await response.json();
    
    if (data.status === 'success' && data.models) {
      return data.models;
    } else {
      throw new Error(data.error || 'Invalid response format');
    }
  } catch (error) {
    console.warn('Failed to load models from API, using defaults:', error);
    // Fallback to default models
    return {
      "gpt-4o": { name: "GPT-4o", provider: "openai" },
      "o3": { name: "o3", provider: "openai" },
      "gpt-4": { name: "GPT-4", provider: "openai" },
    };
  }
};

// --- Alignment Engine API ---

export const alignDraftsAPI = async (
  drafts: AlignmentDraft[], 
  consensusStrategy: string = 'highest_confidence',
  imagePath?: string
): Promise<AlignmentResult> => {
  try {
    console.log(`Aligning ${drafts.length} drafts with strategy: ${consensusStrategy}`);
    if (imagePath) {
      console.log(`Including bounding box detection for image: ${imagePath}`);
    }
    
    const requestBody: any = {
      drafts,
      generate_visualization: true,
      consensus_strategy: consensusStrategy
    };
    
    if (imagePath) {
      requestBody.image_path = imagePath;
    }
    
    const response = await fetch('http://localhost:8000/api/alignment/align-drafts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(requestBody)
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    console.log("Alignment API response:", data);

    return data;
  } catch (error) {
    console.error('Alignment API error:', error);
    return {
      success: false,
      processing_time: 0,
      summary: {
        total_positions: 0,
        total_differences: 0,
        average_confidence: 0,
        quality_assessment: 'Failed',
        high_confidence_positions: 0,
        medium_confidence_positions: 0,
        low_confidence_positions: 0
      },
      error: error instanceof Error ? error.message : 'Unknown alignment error'
    };
  }
}; 