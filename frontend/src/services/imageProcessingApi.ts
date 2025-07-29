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

export const alignDraftsAPI = async (drafts: AlignmentDraft[], consensusStrategy: string = 'highest_confidence'): Promise<AlignmentResult> => {
  try {
    console.log(`Aligning ${drafts.length} drafts with strategy: ${consensusStrategy}`);
    
    const response = await fetch('http://localhost:8000/api/alignment/align-drafts', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        drafts,
        generate_visualization: true,
        consensus_strategy: consensusStrategy
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const data = await response.json();
    console.log("Alignment API response:", data);

    return data;
  } catch (error) {
    console.error('Alignment API error:', error);
    // Fix the property name in the fallback object
    return {
      success: false,
      processing_time: 0,
      summary: {
        total_positions_analyzed: 0,  // ← Fix: Change from total_positions to total_positions_analyzed
        total_differences_found: 0,   // ← Fix: Change from total_differences to total_differences_found
        average_confidence_score: 0,  // ← Fix: Change from average_confidence to average_confidence_score
        quality_assessment: 'Failed',
        confidence_distribution: {     // ← Fix: Use the correct structure
          high: 0,
          medium: 0,
          low: 0
        }
      },
      error: error instanceof Error ? error.message : 'Unknown alignment error'
    };
  }
}; 

// Update the API call to use the new endpoint

export const selectFinalDraftAPI = async (
  redundancyAnalysis: any,
  selectedDraft: number | 'consensus' | 'best',
  alignmentResult?: any,
  editedDraftContent?: string,
  editedFromDraft?: number | 'consensus' | 'best' | null  // Add null here
): Promise<any> => {
  console.log('🎯 Calling selectFinalDraftAPI with:', {
    selectedDraft,
    hasAlignmentResult: !!alignmentResult,
    hasEditedContent: !!editedDraftContent,
    editedFromDraft
  });

  const formData = new FormData();
  formData.append('redundancy_analysis', JSON.stringify(redundancyAnalysis));
  formData.append('selected_draft', selectedDraft.toString());
  
  if (alignmentResult) {
    formData.append('alignment_result', JSON.stringify(alignmentResult));
  }
  if (editedDraftContent) {
    formData.append('edited_draft_content', editedDraftContent);
  }
  if (editedFromDraft !== null && editedFromDraft !== undefined) {  // Check for null explicitly
    formData.append('edited_from_draft', editedFromDraft.toString());
  }

  console.log('📤 Sending FormData with keys:', Array.from(formData.keys()));

  const response = await fetch('http://localhost:8000/api/final-draft/select-final-draft', {
    method: 'POST',
    body: formData
  });

  console.log(' Response status:', response.status, response.statusText);

  if (!response.ok) {
    const errorText = await response.text();
    console.error('❌ API Error Response:', errorText);
    throw new Error(`HTTP error! status: ${response.status} - ${errorText}`);
  }

  const data = await response.json();
  console.log('✅ API Response:', data);
  return data;
}; 